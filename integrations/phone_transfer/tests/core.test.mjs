import test from 'node:test';
import assert from 'node:assert/strict';
import { IncomingTransfer, MAX_FILE, CHUNK, safeFilename, validateFiles, fileDigest, newReceiver, parseToken, tokenFor, proofText, makeProof, verifyProof, receiverDestination } from '../src/core.js';

const missing = () => Object.assign(new Error('Missing'), { name: 'NotFoundError' });
const wrongKind = () => Object.assign(new Error('Wrong entry type'), { name: 'TypeMismatchError' });
class MemoryDirectory {
  constructor(name = 'L') { this.name = name; this.dirs = new Map(); this.files = new Map(); }
  async getDirectoryHandle(name, options = {}) {
    if (this.files.has(name)) throw wrongKind();
    if (!this.dirs.has(name)) { if (!options.create) throw missing(); this.dirs.set(name, new MemoryDirectory(name)); }
    return this.dirs.get(name);
  }
  async getFileHandle(name, options = {}) {
    if (this.dirs.has(name)) throw wrongKind();
    if (!this.files.has(name)) {
      if (!options.create) throw missing();
      const entry = { content: new Uint8Array(), closed: 0, aborts: 0 };
      entry.getFile = async () => new File([entry.corrupt ? 'corrupt' : entry.content], name);
      entry.createWritable = async () => {
        const chunks = [];
        return {
          write: async chunk => { if (entry.writeError) throw new Error('Disk full'); chunks.push(chunk.slice()); },
          close: async () => { entry.content = new Uint8Array(await new Blob(chunks).arrayBuffer()); entry.closed++; },
          abort: async () => { entry.aborts++; },
        };
      };
      this.files.set(name, entry);
    }
    return this.files.get(name);
  }
}
async function deliver(receiver, files) {
  await receiver.begin(files);
  const results = [];
  for (let i = 0; i < files.length; i++) {
    await receiver.start(i);
    for (let offset = 0; offset < files[i].size; offset += CHUNK) await receiver.write(await files[i].slice(offset, offset + CHUNK).arrayBuffer());
    results.push(await receiver.finish(i, await fileDigest(files[i])));
  }
  assert.deepEqual(receiver.complete(), results); return results;
}

test('files stay byte-identical, including HEIC-like bytes, Unicode, zero bytes and duplicate names', async () => {
  const root = new MemoryDirectory(); const events = [];
  const payload = new Uint8Array(CHUNK * 23 + 81); for (let i = 0; i < payload.length; i++) payload[i] = i % 251;
  const files = [new File([payload], '会议照片.heic'), new File(['different'], '会议照片.heic'), new File([], '空文件.txt')];
  const received = await deliver(new IncomingTransfer(root, r => events.push(r)), files);
  assert.equal(events.length, 3); assert.equal(new Set(received.map(r => r.name)).size, 3);
  assert.deepEqual(received.map(r => r.name), ['会议照片.heic', '会议照片 (2).heic', '空文件.txt']);
  assert.equal(root.dirs.size, 0);
  for (let i = 0; i < received.length; i++) {
    assert.equal(received[i].folder, '.');
    const handle = await root.getFileHandle(received[i].name);
    assert.deepEqual(await (await handle.getFile()).arrayBuffer(), await files[i].arrayBuffer());
  }
});
test('re-sending an identical filename adds a suffix in the same folder and never alters the original', async () => {
  const root = new MemoryDirectory();
  const first = await deliver(new IncomingTransfer(root), [new File(['original'], 'IMG_0001.JPG')]);
  const second = await deliver(new IncomingTransfer(root), [new File(['new'], 'IMG_0001.JPG')]);
  assert.equal(first[0].folder, '.'); assert.equal(second[0].folder, '.');
  assert.equal(first[0].name, 'IMG_0001.JPG'); assert.equal(second[0].name, 'IMG_0001 (2).JPG');
  assert.equal(root.dirs.size, 0);
  assert.equal(await (await (await root.getFileHandle(first[0].name)).getFile()).text(), 'original');
});
test('Ding2026 selections use 手机传输 with matching receipts and preserve earlier files across batches', async () => {
  for (const name of ['Ding2026', 'ding2026', 'DING2026']) {
    const root = new MemoryDirectory(name);
    const legacy = await root.getFileHandle('existing.txt', { create: true });
    legacy.content = new TextEncoder().encode('keep');
    assert.deepEqual(receiverDestination(root), { subfolder: '手机传输', label: `${name} / 手机传输` });
    const first = await deliver(new IncomingTransfer(root), [new File(['original'], '照片.HEIC')]);
    const second = await deliver(new IncomingTransfer(root), [new File(['different'], '照片.HEIC')]);
    assert.deepEqual([...root.dirs.keys()], ['手机传输']);
    assert.equal(root.dirs.get('手机传输').dirs.size, 0);
    assert.equal(first[0].name, '照片.HEIC'); assert.equal(second[0].name, '照片 (2).HEIC');
    for (const [result, expected] of [[first[0], 'original'], [second[0], 'different']]) {
      assert.equal(result.folder, '手机传输');
      assert.equal(await (await (await root.dirs.get('手机传输').getFileHandle(result.name)).getFile()).text(), expected);
    }
    assert.equal(await (await legacy.getFile()).text(), 'keep');
  }
});
test('selecting 手机传输 or another folder does not create an extra nested folder', async () => {
  for (const name of ['手机传输', '照片备份', 'Ding2026-backup']) {
    const root = new MemoryDirectory(name);
    assert.deepEqual(receiverDestination(root), { subfolder: '', label: name });
    const [result] = await deliver(new IncomingTransfer(root), [new File(['exact'], 'a.txt')]);
    assert.equal(result.folder, '.'); assert.equal(result.name, 'a.txt');
    assert.equal(root.dirs.size, 0);
    assert.equal(await (await (await root.getFileHandle(result.name)).getFile()).text(), 'exact');
  }
});
test('an unavailable 手机传输 subdirectory fails without writing to Ding2026 itself', async () => {
  const root = new MemoryDirectory('Ding2026'); let receipts = 0;
  root.getDirectoryHandle = async name => { assert.equal(name, '手机传输'); throw new Error('Permission denied'); };
  const receiver = new IncomingTransfer(root, () => receipts++);
  await assert.rejects(receiver.begin([new File(['x'], 'a.txt')]), /Permission denied/);
  assert.equal(root.dirs.size, 0); assert.equal(root.files.size, 0);
  assert.equal(receiver.batch, null); assert.equal(receipts, 0);
});
test('nonempty files, zero-byte files and same-name directories are all preserved', async () => {
  const root = new MemoryDirectory(); const receiver = new IncomingTransfer(root); const file = new File(['new'], 'IMG.JPG');
  await receiver.begin([file]);
  const old = await root.getFileHandle('IMG.JPG', { create: true }); old.content = new TextEncoder().encode('old');
  const empty = await root.getFileHandle('IMG (2).JPG', { create: true });
  const directory = await root.getDirectoryHandle('IMG (3).JPG', { create: true });
  await receiver.start(0); await receiver.write(await file.arrayBuffer());
  const result = await receiver.finish(0, await fileDigest(file));
  assert.equal(result.name, 'IMG (4).JPG'); assert.equal(await (await old.getFile()).text(), 'old');
  assert.equal((await empty.getFile()).size, 0); assert.equal(old.closed, 0); assert.equal(empty.closed, 0);
  assert.equal(root.dirs.get('IMG (3).JPG'), directory);
});
test('retrying after interruption leaves its zero-byte placeholder untouched', async () => {
  const root = new MemoryDirectory(); const first = new IncomingTransfer(root);
  const file = new File(['content'], 'photo.heic');
  await first.begin([file]); await first.start(0); await first.write(await file.arrayBuffer());
  const placeholder = first.active.handle; await first.abort();
  const [result] = await deliver(new IncomingTransfer(root), [file]);
  assert.equal(result.name, 'photo (2).heic'); assert.equal(result.folder, '.');
  assert.equal((await placeholder.getFile()).size, 0); assert.equal(placeholder.closed, 0);
  assert.equal(placeholder.aborts, 1);
});
test('name suffixes preserve final extensions and also support extensionless files', async () => {
  const root = new MemoryDirectory();
  const files = ['README', 'README', '.env', '.env', 'archive.tar.gz', 'archive.tar.gz'].map(name => new File(['x'], name));
  const results = await deliver(new IncomingTransfer(root), files);
  assert.deepEqual(results.map(r => r.name), ['README', 'README (2)', '.env', '.env (2)', 'archive.tar.gz', 'archive.tar (2).gz']);
});
test('rejects oversize, negative, malformed and excessive manifests before any file is created', async () => {
  assert.equal(validateFiles([{ name: 'max', size: MAX_FILE }])[0].size, MAX_FILE);
  for (const files of [[{ name: 'x', size: MAX_FILE + 1 }], [{ name: 'x', size: -1 }], [{ name: '', size: 1 }], [], Array(501).fill({ name: 'a', size: 1 })]) {
    const root = new MemoryDirectory(); await assert.rejects(new IncomingTransfer(root).begin(files)); assert.equal(root.dirs.size, 0);
  }
});
test('checksum mismatch, overrun and premature completion never acknowledge success', async () => {
  let receipts = 0;
  const receiver = new IncomingTransfer(new MemoryDirectory(), () => receipts++);
  await receiver.begin([{ name: 'a', size: 3 }]); await receiver.start(0);
  await assert.rejects(receiver.write(new Uint8Array(4)));
  await receiver.write(new Uint8Array([1, 2, 3]));
  await assert.rejects(receiver.finish(0, '0'.repeat(64)));
  assert.throws(() => receiver.complete()); await receiver.abort(); assert.equal(receipts, 0);
});
test('read-back corruption is detected even when network bytes matched', async () => {
  let receipts = 0;
  const receiver = new IncomingTransfer(new MemoryDirectory(), () => receipts++); const file = new File(['good'], 'a');
  await receiver.begin([file]); await receiver.start(0); await receiver.write(await file.arrayBuffer()); receiver.active.handle.corrupt = true;
  await assert.rejects(receiver.finish(0, await fileDigest(file)), /落盘后校验失败/); assert.equal(receipts, 0);
});
test('disk errors and disconnects keep earlier verified files and abort the unfinished writer', async () => {
  const root = new MemoryDirectory(); let receipts = 0; const receiver = new IncomingTransfer(root, () => receipts++);
  const file = new File(['saved'], 'a'); await receiver.begin([file, file]);
  await receiver.start(0); await receiver.write(await file.arrayBuffer()); await receiver.finish(0, await fileDigest(file));
  await receiver.start(1); const failed = receiver.active.handle; failed.writeError = true;
  await assert.rejects(receiver.write(await file.arrayBuffer()), /Disk full/); await receiver.abort();
  assert.equal(receipts, 1); assert.equal(failed.aborts, 1); assert.equal(failed.closed, 0);
});
test('path separators, Windows device names and bidi characters cannot escape the chosen batch', () => {
  for (const name of ['../../x', 'C:\\Windows\\file', 'CON', 'aux.txt', 'photo\u202Egpj.exe', 'a\0b']) assert.doesNotMatch(safeFilename(name), /[<>:"/\\|?*\u0000\u202e]/);
  assert.equal(safeFilename('CON'), '_CON'); assert.equal(safeFilename('a.jpg'), 'a.jpg');
});
test('the phone token cannot impersonate L; proofs are bound to each live encrypted connection', async () => {
  const receiver = await newReceiver(); const binding = parseToken(tokenFor(receiver.binding));
  assert.equal(receiver.privateKey.extractable, false);
  const transcript = proofText(binding.room, 'receiver-nonce', 'sender-nonce', ['fp-a', 'fp-b']);
  const receiverProof = await makeProof(receiver, transcript);
  assert.equal(await verifyProof(binding, 'receiver', transcript, receiverProof), true);
  assert.equal(await verifyProof(binding, 'sender', transcript, { mac: receiverProof.mac }), false, 'receiver MAC cannot be reflected as a sender proof');
  const sender = { role: 'sender', binding }; const senderProof = await makeProof(sender, transcript);
  assert.equal(await verifyProof(binding, 'sender', transcript, senderProof), true);
  assert.equal(await verifyProof(binding, 'receiver', transcript, senderProof), false);
  assert.equal(await verifyProof(binding, 'receiver', proofText(binding.room, 'other', 'sender-nonce', ['fp-a', 'fp-b']), receiverProof), false);
  assert.equal(await verifyProof(binding, 'receiver', proofText(binding.room, 'receiver-nonce', 'sender-nonce', ['MITM', 'fp-b']), receiverProof), false);
  assert.equal(await verifyProof((await newReceiver()).binding, 'receiver', transcript, receiverProof), false);
});
test('out-of-order headers and unaccepted chunks are rejected', async () => {
  const receiver = new IncomingTransfer(new MemoryDirectory());
  await assert.rejects(receiver.write(new Uint8Array([1]))); await receiver.begin([{ name: 'x', size: 1 }]);
  await assert.rejects(receiver.start(1)); await receiver.start(0); await assert.rejects(receiver.start(0));
});
