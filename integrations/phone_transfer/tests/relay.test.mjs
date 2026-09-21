import test from 'node:test';
import assert from 'node:assert/strict';
import { Cipher, relayKey, StreamlitRelay } from '../src/relay.js';
import { newReceiver, randomHex, CHUNK } from '../src/core.js';

test('encrypted relay keeps 512 KiB binary chunks exact and hides readable content', async () => {
  const { binding } = await newReceiver(); const a = randomHex(16), b = randomHex(16);
  const sender = new Cipher(binding, a, b), receiver = new Cipher(binding, a, b);
  const data = crypto.getRandomValues(new Uint8Array(65536)); const payload = new Uint8Array(CHUNK);
  for (let i = 0; i < payload.length; i += data.length) payload.set(data, i);
  const body = await sender.encrypt(payload);
  assert.ok(body.length < 1500000); assert.deepEqual(new Uint8Array(await receiver.decrypt(body)), payload);
  const secret = '会议资料_保留原件_HEIC_未经压缩';
  const encrypted = await sender.encrypt(secret);
  assert.ok(!Buffer.from(encrypted, 'base64url').includes(Buffer.from(secret)));
  assert.equal(await receiver.decrypt(encrypted), secret);
  assert.notEqual(relayKey(binding), binding.auth);
  assert.equal(relayKey(binding).length, 64);
});
test('relay rejects replay, reorder, tampering, wrong direction and wrong pairing', async () => {
  const { binding } = await newReceiver(); const a = randomHex(16), b = randomHex(16);
  const sender = new Cipher(binding, a, b); const first = await sender.encrypt('first'); const second = await sender.encrypt('second');
  await assert.rejects(new Cipher(binding, a, b).decrypt(second));
  const receiver = new Cipher(binding, a, b); assert.equal(await receiver.decrypt(first), 'first');
  await assert.rejects(receiver.decrypt(first)); assert.equal(await receiver.decrypt(second), 'second');
  const corrupt = Buffer.from(first, 'base64url'); corrupt[corrupt.length - 1] ^= 1;
  await assert.rejects(new Cipher(binding, a, b).decrypt(corrupt.toString('base64url')));
  await assert.rejects(new Cipher(binding, b, a).decrypt(first));
  await assert.rejects(new Cipher((await newReceiver()).binding, a, b).decrypt(first));
});

test('a restarted server clears the old channel instead of reporting L online', async () => {
  const state = { role: 'sender', binding: (await newReceiver()).binding };
  const posts = [], statuses = []; let closed = 0;
  globalThis.window = { parent: { postMessage: value => posts.push(value) } };
  const relay = new StreamlitRelay(state, {
    onPeer: (_id, channel) => { channel.onclose = () => closed++; },
    onStatus: value => statuses.push(value), onError: error => { throw error; },
  });
  try {
    relay.render({ request_id: posts.at(-1).value.request_id, relay: { ok: true, peers: [{ id: randomHex(16), role: 'receiver' }], accepted: [], messages: [] } });
    await relay.receiving;
    clearTimeout(relay.timer); relay.pump();
    relay.render({ request_id: posts.at(-1).value.request_id, relay: { ok: false, error: 'receiver_offline' } });
    await relay.receiving;
    assert.equal(closed, 1); assert.equal(relay.channels.size, 0); assert.equal(statuses.at(-1), true);
  } finally { relay.close(); delete globalThis.window; }
});
