import test from 'node:test';
import assert from 'node:assert/strict';
import { Cipher, relayKey } from '../src/relay.js';
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
