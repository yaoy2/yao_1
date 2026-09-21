import QRCode from 'qrcode';
import { StreamlitRelay } from './relay.js';
import { ShortcutReceiver, shortcutConfig, shortcutInstallLinks } from './shortcuts.js';
import { CHUNK, IncomingTransfer, b64, hex, newReceiver, parseToken, proofText, makeProof, verifyProof, randomHex, receiverDestination, sha256, tokenFor, validateFiles } from './core.js';

const $ = id => document.getElementById(id);
const show = (id, visible = true) => { $(id).hidden = !visible; resize(); };
const status = (text, ready = false) => { $('connection').textContent = text; $('connection').classList.toggle('ready', ready); };
const message = (text, error = false) => { $('message').textContent = text; $('message').classList.toggle('error', error); resize(); };
const size = n => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1024).toFixed(1)} KiB`;
let state, directory, db, relay, reconnectTimer, connected = false, stopped = false, hasLock = false, releaseLock;
let selected = [], sending = false, activeReceiver = null, progressBase = 0, totalBytes = 0, totalSaved = 0, wakeLock;
let pairingUrl = ''; let latestRender = null;
let shortcutReceiver = null;
const peers = new Map();

function resize() {
  if (window.parent !== window) window.parent.postMessage({ isStreamlitMessage: true, type: 'streamlit:setFrameHeight', height: Math.ceil(document.body.scrollHeight + 16) }, '*');
}
if (window.parent !== window) {
  window.parent.postMessage({ isStreamlitMessage: true, type: 'streamlit:componentReady', apiVersion: 1 }, '*');
  window.addEventListener('message', e => {
    if (e.source !== window.parent || e.data?.type !== 'streamlit:render') return;
    latestRender = e.data.args; relay?.render(latestRender); resize();
  });
}
new ResizeObserver(resize).observe(document.body);

async function storage() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('yao-suishouchuan-v1', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('settings');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error('浏览器不能保存绑定信息，请关闭无痕模式后重试'));
  });
}
async function setting(key, value) {
  return new Promise((resolve, reject) => {
    const writing = arguments.length > 1;
    const tx = db.transaction('settings', writing ? 'readwrite' : 'readonly');
    const store = tx.objectStore('settings');
    const req = writing ? value === null ? store.delete(key) : store.put(value, key) : store.get(key);
    tx.oncomplete = () => resolve(req.result);
    tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || new Error('未能保存浏览器设置'));
  });
}
function guard(fn) {
  return async (...args) => { try { await fn(...args); } catch (e) { if (e.name !== 'AbortError') message(e.message || '操作失败，请重试', true); } };
}
function pageUrl() { return new URL('/25_phone_transfer', location.origin).href; }
function readBindingFragment() {
  // Community Cloud nests the app and component in two same-origin frames.
  let host = window;
  for (let depth = 0; depth < 8; depth++) {
    try {
      if (host.location.hash.startsWith('#transfer=')) {
        const token = host.location.hash.slice(10);
        host.history.replaceState(null, '', host.location.pathname + host.location.search);
        return token;
      }
      if (host === host.parent) break;
      host = host.parent;
    } catch { break; }
  }
  return null;
}
function progress(text, done, total) {
  show('progress-box'); $('progress-text').textContent = text;
  const value = total ? Math.min(.99, done / total) : 0;
  $('progress').value = value; $('percentage').textContent = `${Math.floor(value * 100)}%`;
}
function progressDone(text) { show('progress-box'); $('progress-text').textContent = text; $('progress').value = 1; $('percentage').textContent = '100%'; }
function saved(result) {
  const row = document.createElement('li'); const name = document.createElement('span'); const amount = document.createElement('small');
  name.textContent = result.name; name.title = result.folder; amount.textContent = `${size(result.size)} · 已校验`;
  row.append(name, amount); $('history').prepend(row); show('history-box');
  if ($('history').children.length > 100) $('history').lastElementChild.remove();
}
function readyPeer() { return [...peers.values()].find(p => p.authenticated && p.channel?.readyState === 'open'); }
function updatePeerStatus() {
  const ready = readyPeer();
  if (ready) {
    status(state.role === 'receiver' ? '手机已连接' : '办公电脑 L 在线', true);
    if (!sending && !activeReceiver && !$('message').classList.contains('error')) message(state.role === 'receiver' ? '已准备接收，文件会自动保存到所选文件夹。' : '从相册选择照片后发送，电脑会自动保存。');
  } else {
    status(connected ? state.role === 'receiver' ? '等待手机连接' : '等待办公电脑 L' : '连接中');
    if (state.role === 'sender' && !sending && !$('message').classList.contains('error')) message('请在办公电脑 L 保持接收页打开，并确认文件夹已授权。');
  }
  $('pick').disabled = !ready || sending;
  $('pick-photos').disabled = !ready || sending;
  $('send').disabled = !ready || sending || !selected.length;
}
async function keepAwake() {
  try { if (document.visibilityState === 'visible' && navigator.wakeLock && !wakeLock) wakeLock = await navigator.wakeLock.request('screen'); }
  catch { /* Sending still works when the browser does not support Wake Lock. */ }
}
async function releaseAwake() { try { await wakeLock?.release(); } catch { /* Already released. */ } wakeLock = null; }

class Peer {
  constructor(id, channel, localId) {
    this.id = id; this.localId = localId; this.authenticated = false; this.nonce = randomHex(32); this.waiters = new Map(); this.receiveQueue = Promise.resolve(); this.closed = false;
    this.authTimer = setTimeout(() => this.close(new Error('连接超时，请重新打开手机发送页')), 60000);
    this.attach(channel);
  }
  attach(channel) {
    if (this.channel) { channel.close(); return; }
    this.channel = channel; channel.binaryType = 'arraybuffer';
    const greet = () => {
      if (this.helloSent || this.closed) return;
      this.helloSent = true;
      this.json({ type: 'hello', protocol: 'suishou/1', role: state.role, nonce: this.nonce });
    };
    channel.onopen = greet;
    channel.onmessage = e => {
      this.receiveQueue = this.receiveQueue.then(async () => { if (!this.closed) await this.handle(e.data); }).catch(e => this.close(e));
    };
    channel.onclose = () => this.close(new Error('连接中断；已保存文件保留，未完成的文件请重发'));
    channel.onerror = () => this.close(new Error('传输连接发生错误，请重试'));
    if (channel.readyState === 'open') greet();
  }
  json(value) {
    if (this.closed || this.channel?.readyState !== 'open') throw new Error('连接已断开');
    this.channel.send(JSON.stringify(value));
  }
  async handle(data) {
    if (typeof data !== 'string') {
      if (!this.authenticated || !this.incoming) throw new Error('尚未接受这次文件传输');
      await this.incoming.write(data); return;
    }
    if (data.length > 1024 * 1024) throw new Error('传输消息过大');
    const msg = JSON.parse(data);
    if (!this.authenticated) return this.authenticate(msg);
    if (msg.type === 'error') throw new Error(String(msg.message || '对端未完成保存'));
    if (this.waiters.has(msg.type)) { this.waiters.get(msg.type).resolve(msg); return; }
    if (state.role !== 'receiver') throw new Error('未请求的传输消息');
    if (msg.type === 'begin') {
      if (activeReceiver) { this.json({ type: 'error', message: '电脑正在接收另一批文件，请稍后重试' }); return; }
      if (!hasLock || await directory.queryPermission({ mode: 'readwrite' }) !== 'granted') throw new Error('请在 L 恢复保存文件夹授权');
      if (activeReceiver) { this.json({ type: 'error', message: '电脑正在接收另一批文件，请稍后重试' }); return; }
      this.incoming = new IncomingTransfer(directory, saved); activeReceiver = this;
      await this.incoming.begin(msg.files); totalBytes = this.incoming.batch.manifest.reduce((n, f) => n + f.size, 0); progressBase = 0; totalSaved = 0;
      this.json({ type: 'accepted' }); progress('正在接收', 0, totalBytes); message('正在接收；写入并校验完成后才会向手机报告送达。');
    } else if (msg.type === 'file') {
      if (!this.incoming) throw new Error('缺少文件清单');
      await this.incoming.start(msg.index); this.json({ type: 'file-ready', index: msg.index });
    } else if (msg.type === 'checkpoint') {
      if (!this.incoming?.active || msg.offset !== this.incoming.active.received) throw new Error('分段长度校验失败');
      progress(`正在接收 ${this.incoming.active.source.name}`, progressBase + msg.offset, totalBytes);
      this.json({ type: 'checkpoint-ok', offset: msg.offset });
    } else if (msg.type === 'file-end') {
      if (!this.incoming) throw new Error('没有正在接收的文件');
      progress('正在校验电脑上保存的文件', progressBase + this.incoming.active.received, totalBytes);
      const result = await this.incoming.finish(msg.index, msg.sha256);
      progressBase += result.size; totalSaved++;
      this.json({ type: 'saved', index: msg.index, ...result });
    } else if (msg.type === 'batch-end') {
      if (!this.incoming) throw new Error('没有正在接收的文件');
      const results = this.incoming.complete(); this.incoming = null; activeReceiver = null;
      this.json({ type: 'complete', count: results.length });
      progressDone(`已保存 ${results.length} 个文件`); message(`已保存到 ${receiverDestination(directory).label}，全部通过内容校验。`);
    } else throw new Error('无法识别的传输消息');
  }
  async authenticate(msg) {
    if (msg.type === 'hello') {
      if (this.remoteNonce || msg.protocol !== 'suishou/1' || !['receiver', 'sender'].includes(msg.role) || msg.role === state.role || !/^[a-f0-9]{64}$/.test(msg.nonce)) throw new Error('此设备未绑定到办公电脑 L');
      this.remoteNonce = msg.nonce;
      this.transcript = proofText(state.binding.room, state.role === 'receiver' ? this.nonce : msg.nonce, state.role === 'sender' ? this.nonce : msg.nonce, [this.localId, this.id]);
      this.json({ type: 'proof', ...await makeProof(state, this.transcript) });
    } else if (msg.type === 'proof') {
      if (!this.transcript || !await verifyProof(state.binding, state.role === 'receiver' ? 'sender' : 'receiver', this.transcript, msg)) throw new Error('设备身份校验失败，未接收文件');
      this.authenticated = true; clearTimeout(this.authTimer); updatePeerStatus();
    } else throw new Error('设备尚未通过身份校验');
  }
  wait(type, timeout = 120000) {
    if (this.closed) return Promise.reject(new Error('连接已断开'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.waiters.delete(type); reject(new Error('等待电脑保存超时，已保存文件保留，请重试')); }, timeout);
      this.waiters.set(type, { resolve: value => { clearTimeout(timer); this.waiters.delete(type); resolve(value); }, reject: e => { clearTimeout(timer); this.waiters.delete(type); reject(e); } });
    });
  }
  async exchange(message, response) {
    const pending = this.wait(response);
    try { this.json(message); } catch (e) { this.waiters.get(response)?.reject(e); }
    return pending;
  }
  async drain() {
    if (this.closed) throw new Error('连接已断开');
    if (this.channel.bufferedAmount <= 512 * 1024) return;
    await new Promise((resolve, reject) => {
      const channel = this.channel; channel.bufferedAmountLowThreshold = 0;
      const done = e => { clearTimeout(timer); clearInterval(poll); channel.removeEventListener('bufferedamountlow', low); channel.removeEventListener('close', close); e ? reject(e) : resolve(); };
      const low = () => done(); const close = () => done(new Error('连接已断开'));
      const timer = setTimeout(() => done(new Error('网络发送超时')), 30000);
      const poll = setInterval(() => { if (channel.bufferedAmount === 0) done(); }, 100);
      channel.addEventListener('bufferedamountlow', low, { once: true }); channel.addEventListener('close', close, { once: true });
    });
  }
  close(error) {
    if (this.closed) return;
    const wasBusy = !!this.incoming || sending;
    try { if (this.authenticated && this.channel?.readyState === 'open' && error) this.json({ type: 'error', message: error.message }); } catch { /* Already disconnected. */ }
    this.closed = true; this.authenticated = false; clearTimeout(this.authTimer);
    for (const waiter of [...this.waiters.values()]) waiter.reject(error || new Error('连接已关闭'));
    if (this.incoming) {
      const incoming = this.incoming;
      // Let already-queued disk writes settle before closing the writer.
      this.receiveQueue.finally(() => incoming.abort()).catch(() => {});
      this.incoming = null;
    }
    if (activeReceiver === this) activeReceiver = null;
    this.channel?.close(); peers.delete(this.id); updatePeerStatus();
    if (error && wasBusy) message(error.message, true);
    if (error && !stopped && !peers.size) reconnect();
  }
}
function reconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => { const old = relay; relay = null; old?.close(); connected = false; connect(); }, 2000);
}
function connect() {
  if (!state || stopped || relay || state.role === 'receiver' && !hasLock) return;
  if (window.parent === window) { message('请通过工具箱的“随手传”页面打开。', true); return; }
  status('连接中');
  relay = new StreamlitRelay(state, {
    onPeer: (id, channel, localId) => { if (!peers.has(id)) peers.set(id, new Peer(id, channel, localId)); },
    onStatus: online => { connected = online; updatePeerStatus(); },
    onError: error => {
      message(error.message, true);
      for (const peer of [...peers.values()]) peer.close(error);
      reconnect();
    },
  });
  if (latestRender) relay.render(latestRender);
}
function disconnect() {
  stopped = true; clearTimeout(reconnectTimer);
  shortcutReceiver?.stop(); shortcutReceiver = null;
  const old = relay; relay = null; old?.close();
  for (const peer of [...peers.values()]) peer.close();
  connected = false;
}

async function acquireReceiverLock() {
  if (hasLock) return true;
  if (!navigator.locks) throw new Error('当前浏览器不支持安全接收，请在 L 使用新版 Edge 或 Chrome');
  return new Promise((resolve, reject) => {
    navigator.locks.request('suishouchuan-receiver', { ifAvailable: true }, async lock => {
      if (!lock) { message('另一个标签页正在接收。请先关闭原接收页，再点“恢复文件夹授权”。'); show('resume'); resolve(false); return; }
      hasLock = true; resolve(true);
      await new Promise(release => { releaseLock = release; });
      hasLock = false;
    }).catch(reject);
  });
}
async function activate() {
  stopped = false;
  show('welcome', !state); show('receiver', state?.role === 'receiver'); show('sender', state?.role === 'sender'); show('reset', !!state);
  if (!state) { status('等待首次绑定'); return; }
  if (state.role === 'receiver') {
    $('destination').textContent = directory ? `保存位置：${receiverDestination(directory).label}` : '尚未选择保存文件夹';
    if (!directory || await directory.queryPermission({ mode: 'readwrite' }) !== 'granted') {
      status('等待文件夹授权'); show('resume'); message('点“恢复文件夹授权”，允许网页将文件保存到办公电脑 L。'); return;
    }
    if (!await acquireReceiverLock()) return;
    show('resume', false);
    if (!state.shortcutReceiverToken || !state.binding.nativeRoom) {
      state.shortcutReceiverToken ||= randomHex(32);
      state.binding.nativeRoom = hex(sha256(new TextEncoder().encode(state.shortcutReceiverToken)));
      await setting('state', state);
    }
    if (!shortcutReceiver) shortcutReceiver = new ShortcutReceiver(state, {
      canReceive: () => hasLock && !activeReceiver && !sending,
      onStatus: text => { $('shortcut-status').textContent = text; resize(); },
      onError: error => { message(`${error.message}；处理后点“恢复文件夹授权”重试。`, true); show('resume'); },
      receipt: async (id, result) => {
        const receipts = await setting('shortcut-receipts') || {};
        if (!result) return receipts[id];
        receipts[id] = result;
        for (const key of Object.keys(receipts).slice(0, -1000)) delete receipts[key];
        await setting('shortcut-receipts', receipts);
      },
      receive: receiveShortcutFile,
    });
    shortcutReceiver.start();
  }
  connect();
}
async function receiveShortcutFile(file, getStream) {
  if (activeReceiver || !hasLock) throw new Error('电脑正在接收另一批文件');
  if (await directory.queryPermission({ mode: 'readwrite' }) !== 'granted') throw new Error('请恢复保存文件夹授权');
  if (activeReceiver || !hasLock) throw new Error('电脑正在接收另一批文件');
  const incoming = new IncomingTransfer(directory, saved); activeReceiver = incoming;
  let reader;
  try {
    await incoming.begin([{ name: file.name, size: file.size }]); await incoming.start(0);
    progress(`正在接收相册照片 ${file.name}`, 0, file.size);
    reader = (await getStream()).getReader(); let received = 0;
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      for (let offset = 0; offset < value.length; offset += CHUNK) {
        const chunk = value.subarray(offset, offset + CHUNK); await incoming.write(chunk); received += chunk.length;
      }
      progress(`正在接收 ${file.name}`, received, file.size);
    }
    const result = await incoming.finish(0, file.sha256); incoming.complete();
    progressDone('相册文件已保存并校验'); message(`已保存到 ${receiverDestination(directory).label}。`);
    return result;
  } catch (error) { await incoming.abort(); throw error; }
  finally { await reader?.cancel().catch(() => {}); reader?.releaseLock(); if (activeReceiver === incoming) activeReceiver = null; }
}
async function pair() {
  if (state?.role !== 'receiver') return;
  // Going through the Streamlit page registers the component after a server
  // restart. A bookmarked raw /component/... URL can otherwise return 404.
  const senderUrl = new URL('/25_phone_transfer', location.origin);
  pairingUrl = `${senderUrl.href}#transfer=${tokenFor(state.binding)}`;
  await QRCode.toCanvas($('qr'), pairingUrl, { width: 240, margin: 2, errorCorrectionLevel: 'M' }); show('pairing');
}
async function chooseFolder() {
  if (sending || activeReceiver) throw new Error('请等待本批文件传输完成后再更换文件夹');
  if (!window.showDirectoryPicker) throw new Error('请在办公电脑 L 的 Edge 或 Chrome 中设置接收');
  let picked;
  try { picked = await window.showDirectoryPicker({ id: 'suishouchuan-L', mode: 'readwrite', startIn: 'pictures' }); }
  catch (e) {
    if (e.name === 'SecurityError') throw new Error('未能打开保存文件夹。请直接在 L 的新版 Edge 或 Chrome 打开工具箱后重试。');
    throw e;
  }
  // Keep the previous binding and directory if the user cancels or storage fails.
  const next = state?.role === 'receiver' ? state : await newReceiver();
  await setting('directory', picked); await setting('state', next);
  directory = picked; state = next; message('已记住所选文件夹，正在准备接收。'); await activate(); await pair();
}
async function join(raw) {
  if (state?.role === 'receiver') throw new Error('此浏览器已是办公电脑 L，无需扫描自己的二维码');
  if (sending) throw new Error('请先完成当前发送');
  const binding = parseToken(raw);
  const imported = await crypto.subtle.importKey('raw', Uint8Array.from(atob(binding.publicKey.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0)), { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
  if (!imported) throw new Error('电脑绑定信息无效');
  disconnect(); state = { role: 'sender', binding }; await setting('state', state); show('join', false);
  message('绑定完成，正在连接办公电脑 L。'); await activate();
  setupShortcut();
}
async function sendFiles() {
  const peer = readyPeer();
  if (!peer || !selected.length || sending) return;
  const manifest = validateFiles(selected);
  sending = true; updatePeerStatus(); await keepAwake();
  const total = manifest.reduce((n, f) => n + f.size, 0); let sentBytes = 0, count = 0;
  try {
    await peer.exchange({ type: 'begin', files: manifest }, 'accepted');
    for (let i = 0; i < selected.length; i++) {
      const file = selected[i]; const hasher = sha256.create(); let sinceCheckpoint = 0;
      const ready = await peer.exchange({ type: 'file', index: i }, 'file-ready');
      if (ready.index !== i) throw new Error('电脑响应的文件顺序不正确');
      for (let offset = 0; offset < file.size; offset += CHUNK) {
        const chunk = new Uint8Array(await file.slice(offset, offset + CHUNK).arrayBuffer());
        hasher.update(chunk); await peer.drain(); peer.channel.send(chunk); sinceCheckpoint += chunk.length;
        const end = offset + chunk.length;
        if (sinceCheckpoint >= 2 * 1024 * 1024 || end === file.size) {
          const receipt = await peer.exchange({ type: 'checkpoint', offset: end }, 'checkpoint-ok');
          if (receipt.offset !== end) throw new Error('接收进度不一致');
          progress(`正在发送 ${file.name}`, sentBytes + end, total); sinceCheckpoint = 0;
        }
      }
      const digest = hex(hasher.digest());
      progress(`等待电脑保存并校验 ${file.name}`, sentBytes + file.size, total);
      const receipt = await peer.exchange({ type: 'file-end', index: i, sha256: digest }, 'saved');
      if (receipt.index !== i || receipt.sha256 !== digest || receipt.size !== file.size) throw new Error('电脑保存结果未通过核对');
      sentBytes += file.size; count++; saved(receipt);
    }
    const done = await peer.exchange({ type: 'batch-end' }, 'complete');
    if (done.count !== selected.length) throw new Error('部分文件未收到保存回执');
    progressDone(`已送达办公电脑 L · ${count} 个文件`); message(`电脑已保存 ${count} 个文件，内容校验全部通过。`);
    selected = []; $('files').value = ''; $('photos').value = ''; $('selection').replaceChildren(); show('send', false);
  } catch (e) {
    peer.close(e); message(`${e.message}。本批已确认保存 ${count}/${manifest.length} 个文件；重新发送会另存，不会覆盖。`, true);
  } finally { sending = false; await releaseAwake(); $('pick').disabled = !readyPeer(); $('pick-photos').disabled = !readyPeer(); $('send').disabled = !readyPeer(); }
}

$('setup').onclick = guard(chooseFolder);
$('folder').onclick = guard(chooseFolder);
$('resume').onclick = guard(async () => {
  if (!directory) return chooseFolder();
  if (await directory.requestPermission({ mode: 'readwrite' }) !== 'granted') throw new Error('未获得文件夹写入权限');
  message('文件夹已授权，正在准备接收。');
  await activate();
});
$('pair').onclick = guard(pair);
$('close-pair').onclick = () => show('pairing', false);
function setupShortcut() {
  if (!state) return;
  const config = shortcutConfig(state.binding);
  const links = shortcutInstallLinks(state.binding);
  $('shortcut-download').href = links.download; $('shortcut-check').href = links.check;
  $('shortcut-config').value = links.configuration;
  $('shortcut-url').value = config.url; $('shortcut-authorization').value = config.authorization;
  show('shortcut-instructions');
  $('shortcut-instructions').scrollIntoView({ block: 'start' });
}
$('shortcut-setup').onclick = guard(setupShortcut);
$('shortcut-close').onclick = () => show('shortcut-instructions', false);
$('shortcut-copy-config').onclick = guard(async () => {
  try {
    await navigator.clipboard.writeText($('shortcut-config').value);
    show('shortcut-copy-fallback', false);
    $('shortcut-copy-status').textContent = '绑定码已复制。下载 v4，在安装设置的输入框中长按 → 粘贴。';
  } catch {
    show('shortcut-copy-fallback');
    $('shortcut-config').focus(); $('shortcut-config').select();
    $('shortcut-copy-status').textContent = '浏览器未允许自动复制。请长按下面的绑定码，选“全选 → 复制”，再下载 v4。';
  }
  resize();
});
$('shortcut-copy-url').onclick = guard(async () => { await navigator.clipboard.writeText($('shortcut-url').value); message('已复制快捷指令的准备地址。'); });
$('shortcut-copy-token').onclick = guard(async () => { await navigator.clipboard.writeText($('shortcut-authorization').value); message('已复制授权值，只粘贴到你自己的快捷指令中。'); });
$('copy').onclick = guard(async () => { await navigator.clipboard.writeText(pairingUrl); message('绑定链接已复制，请仅交给自己的手机。'); });
$('enter-code').onclick = () => show('join');
$('cancel-join').onclick = () => show('join', false);
$('bind').onclick = guard(() => join($('token').value));
$('pick').onclick = () => { $('files').value = ''; $('files').click(); };
$('pick-photos').onclick = () => { $('photos').value = ''; $('photos').click(); };
const selectFiles = guard(event => {
  const files = Array.from(event.target.files);
  if (!files.length) return;
  selected = []; $('selection').replaceChildren(); show('send', false);
  validateFiles(files); selected = files;
  for (const file of files) { const row = document.createElement('li'); const label = document.createElement('span'); const amount = document.createElement('small'); label.textContent = file.name; amount.textContent = size(file.size); row.append(label, amount); $('selection').append(row); }
  show('send'); $('send').disabled = !readyPeer(); message(`已选择 ${files.length} 个文件，${size(files.reduce((n, f) => n + f.size, 0))}。`);
});
$('files').onchange = selectFiles;
$('photos').onchange = selectFiles;
$('send').onclick = guard(sendFiles);
$('reset').onclick = guard(async () => {
  if (sending || activeReceiver) throw new Error('请先完成当前传输');
  if (!confirm(state.role === 'receiver' ? '解除 L 的绑定后，手机必须重新扫码。已保存文件保留。继续？' : '解除此浏览器与 L 的绑定？')) return;
  disconnect(); releaseLock?.(); await setting('state', null); await setting('directory', null); state = null; directory = null;
  message('已解除此浏览器绑定，可重新设置。');
  show('pairing', false); show('shortcut-instructions', false); show('progress-box', false); $('history').replaceChildren(); show('history-box', false); await activate();
});
$('standalone').href = pageUrl();
$('standalone').onclick = event => {
  if (activeReceiver) { event.preventDefault(); message('请先完成本批接收，再打开独立接收窗口。', true); return; }
  disconnect(); releaseLock?.(); releaseLock = null;
  show('resume'); status('接收已移到独立窗口'); message('在新窗口保持接收即可。当前标签页可以切换到其他模块。');
};
// Offer a dedicated receiving tab before setup as well.
const welcomeStandalone = $('standalone').cloneNode(true); welcomeStandalone.removeAttribute('id'); $('welcome').append(welcomeStandalone);
window.addEventListener('online', () => { connect(); });
window.addEventListener('beforeunload', e => { if (sending || activeReceiver) { e.preventDefault(); e.returnValue = ''; } });
window.addEventListener('pagehide', () => { disconnect(); releaseLock?.(); });
window.addEventListener('pageshow', event => {
  if (event.persisted && state) guard(async () => {
    hasLock = false; releaseLock = null; await activate();
  })();
});
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { if (sending) { wakeLock = null; keepAwake(); } connect(); } });

guard(async () => {
  if (!window.isSecureContext || !crypto.subtle) throw new Error('请通过 HTTPS 打开工具箱');
  db = await storage(); state = await setting('state'); directory = await setting('directory');
  const fragment = readBindingFragment();
  if (fragment) {
    try { await join(fragment); } catch (error) { await activate(); throw error; }
  } else await activate();
})();
