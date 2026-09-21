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
      res.end(`<!doctype html><html><body><iframe id="component" src="${inner}" style="border:0;width:100%;height:850px" sandbox="allow-same-origin allow-scripts allow-forms allow-modals allow-popups allow-downloads"></iframe>${bridge}</body></html>`); return;
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
  await sender.locator('#files').setInputFiles([{ name: '同名照片.HEIC', mimeType: 'image/heic', buffer: Buffer.from([0, 1, 2, 255]) }, { name: '同名照片.HEIC', mimeType: 'image/heic', buffer: Buffer.from([9, 8, 7, 0]) }]);
  await sender.locator('#send').click();
  await sender.waitForFunction(() => document.getElementById('progress-text').textContent.includes('已送达办公电脑 L · 2 个文件'), null, { timeout: 60000 });
  assert.equal(await frame.locator('#history li').count(), 3);
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
  console.log(JSON.stringify({ result: 'PASS', testFileMiB: mb, sha256Matches: true, duplicateFilesSavedSeparately: true, persistedPairing: true, singleReceiverLock: true, encryptedStreamlitRelay: true, simulatedRoundTripMs: Number(process.env.TRANSFER_LATENCY_MS || 100), screenshots: ['test-output-可删/receiver.png', 'test-output-可删/sender.png'] }));
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
