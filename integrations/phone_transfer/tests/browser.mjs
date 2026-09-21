import http from 'node:http';
import { readFile, mkdir, open, unlink } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

const { chromium } = await import(process.env.TRANSFER_PLAYWRIGHT ? pathToFileURL(process.env.TRANSFER_PLAYWRIGHT).href : 'playwright');
const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(project, 'test-output-可删'); await mkdir(output, { recursive: true });
const python = spawn(process.env.TRANSFER_PYTHON || path.join(project, '../../.venv/Scripts/python.exe'), ['-u', path.join(project, 'tests/relay_bridge.py')], { stdio: ['pipe', 'pipe', 'inherit'] });
const calls = new Map(); let callId = 0;
createInterface({ input: python.stdout }).on('line', line => { const { id, response } = JSON.parse(line); calls.get(id)?.(response); calls.delete(id); });
function exchange(request) { return new Promise(resolve => { const id = ++callId; calls.set(id, resolve); python.stdin.write(JSON.stringify({ id, request }) + '\n'); }); }

const server = http.createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (pathname.startsWith('/phone-transfer-api/v1/')) {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const response = await exchange({ kind: 'native', method: req.method, path: req.url, headers: req.headers, bodyBase64: Buffer.concat(chunks).toString('base64') });
      res.writeHead(response.status, response.headers); res.end(Buffer.from(response.bodyBase64, 'base64')); return;
    }
    if (pathname === '/exchange') {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const request = JSON.parse(Buffer.concat(chunks).toString());
      const response = await exchange(request);
      // Simulate WAN/fragment turnaround without starting a Streamlit server.
      await new Promise(resolve => setTimeout(resolve, Number(process.env.TRANSFER_LATENCY_MS || 100)));
      res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ relay: response, request_id: request.request_id })); return;
    }
    if (pathname === '/frame' || pathname === '/25_phone_transfer') {
      res.setHeader('Content-Type', 'text/html');
      const inner = pathname === '/25_phone_transfer' ? '/frame' : '/index.html';
      const bridge = pathname === '/frame' ? `<script>window.addEventListener('message',async e=>{
        if(e.source!==document.querySelector('iframe').contentWindow)return;
        if(e.data.type==='streamlit:componentReady')e.source.postMessage({type:'streamlit:render',args:{}},'*');
        if(e.data.type!=='streamlit:setComponentValue')return;
        const args=await(await fetch('/exchange',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(e.data.value)})).json();
        e.source.postMessage({type:'streamlit:render',args},'*');
      });</script>` : '';
      res.end(`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><iframe id="component" src="${inner}" style="border:0;width:100%;height:850px" sandbox="allow-same-origin allow-scripts allow-forms allow-modals allow-popups allow-downloads"></iframe>${bridge}</body></html>`); return;
    }
    const name = pathname === '/' ? 'index.html' : pathname.slice(1);
    if (!['index.html', 'app.js', 'style.css'].includes(name)) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html');
    res.end(await readFile(path.join(project, 'frontend', name)));
  } catch { res.writeHead(500).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, executablePath: process.env.TRANSFER_BROWSER });
const errors = []; const created = [];
try {
  const receiverContext = await browser.newContext({ viewport: { width: 1100, height: 920 } });
  await receiverContext.addInitScript(() => {
    window.showDirectoryPicker = async () => (await navigator.storage.getDirectory()).getDirectoryHandle('L-test', { create: true });
    window.confirm = () => true;
  });
  const receiver = await receiverContext.newPage(); receiver.on('pageerror', e => errors.push(e.message));
  await receiver.goto(`${url}/frame`);
  const frame = receiver.frames().find(f => f.url().endsWith('/index.html'));
  await frame.locator('#setup').click();
  await frame.locator('#pairing').waitFor({ state: 'visible' });
  const binding = await frame.evaluate(async () => {
    const db = await new Promise(r => { const req = indexedDB.open('yao-suishouchuan-v1', 1); req.onsuccess = () => r(req.result); });
    return new Promise(r => { const req = db.transaction('settings').objectStore('settings').get('state'); req.onsuccess = () => r(req.result.binding); });
  });
  const token = Buffer.from(JSON.stringify(binding)).toString('base64url');
  await frame.locator('#close-pair').click();
  const senderContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const senderPage = await senderContext.newPage(); senderPage.on('pageerror', e => errors.push(e.message));
  const connectionStarted = Date.now();
  await senderPage.goto(`${url}/25_phone_transfer#transfer=${token}`);
  let sender = senderPage.frames().find(f => f.url().endsWith('/index.html'));
  await sender.waitForFunction(() => document.getElementById('connection').textContent === '办公电脑 L 在线', null, { timeout: 90000 });
  console.log('Authenticated browser connection established in seconds:', (Date.now() - connectionStarted) / 1000);
  assert.equal(new URL(senderPage.url()).hash, '');
  const mb = Number(process.env.TRANSFER_TEST_MIB || 200);
  const filepath = path.join(output, `${randomUUID()}-${mb}MiB.bin`); created.push(filepath);
  const file = await open(filepath, 'wx'); const chunk = Buffer.alloc(1024 * 1024); for (let i = 0; i < chunk.length; i++) chunk[i] = i % 251;
  const digest = createHash('sha256');
  try { for (let i = 0; i < mb; i++) { await file.write(chunk); digest.update(chunk); } } finally { await file.close(); }
  await sender.locator('#files').setInputFiles(filepath);
  const transferStarted = Date.now();
  await sender.locator('#send').click();
  await sender.waitForFunction(() => document.getElementById('progress-text').textContent.startsWith('已送达办公电脑 L') || document.getElementById('message').classList.contains('error'), null, { timeout: 600000 });
  assert.match(await sender.locator('#progress-text').textContent(), /^已送达办公电脑 L/, await sender.locator('#message').textContent());
  console.log('File saved and verified in seconds:', (Date.now() - transferStarted) / 1000);
  const expectedHash = digest.digest('hex');
  const saved = await frame.evaluate(async () => {
    const root = await (await navigator.storage.getDirectory()).getDirectoryHandle('L-test'); const files = [];
    for await (const day of root.values()) for await (const batch of day.values()) for await (const entry of batch.values()) {
      const f = await entry.getFile(); const hash = await crypto.subtle.digest('SHA-256', await f.arrayBuffer());
      files.push({ name: f.name, size: f.size, hash: Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('') });
    }
    return files;
  });
  assert.equal(saved.length, 1); assert.equal(saved[0].size, mb * 1024 * 1024); assert.equal(saved[0].hash, expectedHash);
  const photoChooser = senderPage.waitForEvent('filechooser');
  await sender.locator('#pick-photos').click();
  await (await photoChooser).setFiles([{ name: '同名照片.HEIC', mimeType: 'image/heic', buffer: Buffer.from([0, 1, 2, 255]) }, { name: '同名照片.HEIC', mimeType: 'image/heic', buffer: Buffer.from([9, 8, 7, 0]) }]);
  await sender.locator('#send').click();
  await sender.waitForFunction(() => document.getElementById('progress-text').textContent.includes('已送达办公电脑 L · 2 个文件'), null, { timeout: 60000 });
  assert.equal(await frame.locator('#history li').count(), 3);
  // Exercise the actual ShortcutReceiver against the production ASGI routes.
  // Only the iPhone HTTP upload is simulated; L downloads, verifies, saves and
  // acknowledges through its real frontend and OPFS directory handle.
  await frame.waitForFunction(() => document.getElementById('shortcut-status').textContent === '相册分享已就绪', null, { timeout: 30000 });
  await sender.locator('#shortcut-setup').click();
  const nativeUploadUrl = await sender.locator('#shortcut-url').inputValue();
  const nativeUploadAuthorization = await sender.locator('#shortcut-authorization').inputValue();
  const nativeState = await frame.evaluate(async () => {
    const db = await new Promise(resolve => { const req = indexedDB.open('yao-suishouchuan-v1', 1); req.onsuccess = () => resolve(req.result); });
    return new Promise(resolve => { const req = db.transaction('settings').objectStore('settings').get('state'); req.onsuccess = () => resolve({ room: req.result.binding.nativeRoom, receiverToken: req.result.shortcutReceiverToken }); });
  });
  assert.ok(new URL(nativeUploadUrl).pathname === `/phone-transfer-api/v1/upload/${nativeState.room}`, 'Shortcut URL must address the bound native receiver room');
  assert.ok(nativeUploadAuthorization !== `Bearer ${nativeState.receiverToken}`, 'Shortcut must never receive the L-only read token');
  const expectedUploadToken = createHash('sha256').update(`suishou-shortcut-upload-v1:${binding.room}:${binding.auth}`).digest('hex');
  assert.ok(nativeUploadAuthorization === `Bearer ${expectedUploadToken}`, 'Shortcut authorization must match the derived send-only token');
  assert.ok(await sender.evaluate(() => innerWidth <= 390 && document.documentElement.scrollWidth <= innerWidth), 'Shortcut setup should fit the phone width even with its long address and authorization fields');
  const nativePayloads = [Buffer.alloc(700 * 1024 + 17), Buffer.from([0, 0, 0, 24, 102, 116, 121, 112, 104, 101, 105, 99, 9, 8, 7, 0, 255])];
  for (let i = 0; i < nativePayloads[0].length; i++) nativePayloads[0][i] = i % 239;
  nativePayloads[0].set(Buffer.from([0, 0, 0, 24, 102, 116, 121, 112, 104, 101, 105, 99]), 0);
  const nativeDigests = nativePayloads.map(data => createHash('sha256').update(data).digest('hex'));
  const nativeFilename = '快捷指令同名照片.HEIC';
  for (let i = 0; i < nativePayloads.length; i++) {
    const form = new FormData(); form.append('file', new Blob([nativePayloads[i]], { type: 'image/heic' }), nativeFilename);
    const response = await fetch(nativeUploadUrl, { method: 'POST', headers: { Authorization: nativeUploadAuthorization }, body: form });
    assert.equal(response.status, 202); assert.match(await response.text(), /等待办公电脑 L 保存/);
    await frame.waitForFunction(count => document.querySelectorAll('#history li').length === count, 4 + i, { timeout: 30000 });
    const deadline = Date.now() + 15000; let pending;
    do {
      const response = await fetch(`${url}/phone-transfer-api/v1/receivers/${nativeState.room}/pending`, { headers: { Authorization: `Bearer ${nativeState.receiverToken}` } });
      assert.equal(response.status, 200); pending = (await response.json()).files;
      if (pending.length) await new Promise(resolve => setTimeout(resolve, 100));
    } while (pending.length && Date.now() < deadline);
    assert.deepEqual(pending, [], 'L must acknowledge and remove each staged native upload');
  }
  const afterNative = await frame.evaluate(async () => {
    const root = await (await navigator.storage.getDirectory()).getDirectoryHandle('L-test'); const files = [];
    for await (const day of root.values()) for await (const batch of day.values()) for await (const entry of batch.values()) {
      const file = await entry.getFile(), content = await file.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', content);
      files.push({ path: `${day.name}/${batch.name}/${file.name}`, name: file.name, size: file.size, hash: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('') });
    }
    return files;
  });
  assert.equal(afterNative.length, 5);
  assert.ok(afterNative.some(file => file.size === mb * 1024 * 1024 && file.hash === expectedHash), 'Earlier browser transfer must remain unchanged');
  const nativeSaved = afterNative.filter(file => file.name.endsWith(nativeFilename));
  assert.equal(nativeSaved.length, 2); assert.notEqual(nativeSaved[0].path, nativeSaved[1].path);
  for (let i = 0; i < nativePayloads.length; i++) assert.ok(nativeSaved.some(file => file.size === nativePayloads[i].length && file.hash === nativeDigests[i]), 'Native upload bytes must remain identical in OPFS');
  await sender.locator('#shortcut-close').click();
  console.log('Native Shortcut API: real L frontend saved both same-name originals, SHA-256 matched, queues acknowledged and cleared.');
  assert.ok(await sender.evaluate(() => innerWidth <= 390 && document.documentElement.scrollWidth <= innerWidth), 'Mobile receiver page should fit the phone width');
  await receiver.screenshot({ path: path.join(output, 'receiver.png'), fullPage: true });
  await senderPage.screenshot({ path: path.join(output, 'sender.png'), fullPage: true });
  // Refresh preserves the phone identity and reconnects without re-pairing.
  await senderPage.reload(); sender = senderPage.frames().find(f => f.url().endsWith('/index.html'));
  await sender.waitForFunction(() => document.getElementById('connection').textContent === '办公电脑 L 在线', null, { timeout: 90000 });
  // BFCache-style pagehide/pageshow must restart the connection, not remain stopped.
  await sender.evaluate(() => { window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true })); });
  await sender.evaluate(() => { window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })); });
  await sender.waitForFunction(() => document.getElementById('connection').textContent === '办公电脑 L 在线', null, { timeout: 90000 });
  // A second receiver tab must not become a concurrent disk writer.
  const second = await receiverContext.newPage(); await second.goto(`${url}/frame`);
  await second.frames().find(f => f.url().endsWith('/index.html')).waitForFunction(() => document.getElementById('message').textContent.includes('另一个标签页正在接收'));
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ result: 'PASS', testFileMiB: mb, sha256Matches: true, duplicateFilesSavedSeparately: true, persistedPairing: true, singleReceiverLock: true, encryptedStreamlitRelay: true, nativeShortcutApi: true, nativeExactBytes: true, nativeDuplicateNamesSeparate: true, nativePendingCleared: true, simulatedRoundTripMs: Number(process.env.TRANSFER_LATENCY_MS || 100), screenshots: ['test-output-可删/receiver.png', 'test-output-可删/sender.png'] }));
} catch (error) {
  const pages = browser.contexts().flatMap(c => c.pages());
  for (let i = 0; i < pages.length; i++) {
    console.log(`Page ${i}:`, await pages[i].locator('body').innerText().catch(() => 'unavailable'));
    for (const frame of pages[i].frames().slice(1)) console.log('Frame:', await frame.locator('body').innerText().catch(() => 'unavailable'));
    await pages[i].screenshot({ path: path.join(output, `failure-${i}.png`) }).catch(() => {});

  }
  throw error;
} finally {
  await browser.close(); server.close(); python.kill();
  for (const file of created) if (path.dirname(file) === output) await unlink(file).catch(() => {});
}
