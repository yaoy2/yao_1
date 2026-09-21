import test from 'node:test';
import assert from 'node:assert/strict';
import { IncomingTransfer, MAX_FILE, CHUNK, safeFilename, validateFiles, fileDigest, newReceiver, parseToken, tokenFor, proofText, makeProof, verifyProof } from '../src/core.js';

const missing = () => Object.assign(new Error('Missing'), { name: 'NotFoundError' });
class MemoryDirectory {
  constructor(name = 'L') { this.name = name; this.dirs = new Map(); this.files = new Map(); }
  async getDirectoryHandle(name, options = {}) {
    if (!this.dirs.has(name)) { if (!options.create) throw missing(); this.dirs.set(name, new MemoryDirectory(name)); }
    return this.dirs.get(name);
  }
  async getFileHandle(name, options = {}) {
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
  for (let i = 0; i < received.length; i++) {
    const [day, batch] = received[i].folder.split('/');
    const handle = await (await (await root.getDirectoryHandle(day)).getDirectoryHandle(batch)).getFileHandle(received[i].name);
    assert.deepEqual(await (await handle.getFile()).arrayBuffer(), await files[i].arrayBuffer());
  }
});
test('re-sending an identical filename allocates a different batch and never alters the original', async () => {
  const root = new MemoryDirectory();
  const first = await deliver(new IncomingTransfer(root), [new File(['original'], 'IMG_0001.JPG')]);
  const second = await deliver(new IncomingTransfer(root), [new File(['new'], 'IMG_0001.JPG')]);
  assert.notEqual(first[0].folder, second[0].folder);
  const [day, batch] = first[0].folder.split('/');
  assert.equal(await (await (await root.dirs.get(day).dirs.get(batch).getFileHandle(first[0].name)).getFile()).text(), 'original');
});
test('same-batch collisions use a fresh name and leave preexisting files alone', async () => {
  const receiver = new IncomingTransfer(new MemoryDirectory()); const file = new File(['new'], 'IMG.JPG');
  await receiver.begin([file]);
  const old = await receiver.batch.directory.getFileHandle('001_IMG.JPG', { create: true }); old.content = new TextEncoder().encode('old');
  await receiver.start(0); await receiver.write(await file.arrayBuffer());
  const result = await receiver.finish(0, await fileDigest(file));
  assert.notEqual(result.name, '001_IMG.JPG'); assert.equal(await (await old.getFile()).text(), 'old');
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
