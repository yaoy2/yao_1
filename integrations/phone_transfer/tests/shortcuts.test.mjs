import test from 'node:test';
import assert from 'node:assert/strict';
import { hex, sha256, newReceiver, parseToken, tokenFor } from '../src/core.js';
import { shortcutApiBase, shortcutUploadToken, shortcutInstallLinks, ShortcutReceiver } from '../src/shortcuts.js';

test('native binding commits to the receiver secret without sharing it with the phone', async () => {
  const state = await newReceiver();
  const phone = parseToken(tokenFor(state.binding));
  assert.equal(phone.nativeRoom, hex(sha256(new TextEncoder().encode(state.shortcutReceiverToken))));
  assert.ok(!JSON.stringify(phone).includes(state.shortcutReceiverToken));
  assert.notEqual(shortcutUploadToken(phone), state.shortcutReceiverToken);
  assert.equal(shortcutUploadToken(phone), shortcutUploadToken(state.binding));
});

test('API addresses target the Cloud application rather than the HTML wrapper', () => {
  assert.equal(shortcutApiBase('https://whatsup.streamlit.app/~/+/component/example/index.html'), 'https://whatsup.streamlit.app/~/+/phone-transfer-api/v1');
  assert.equal(shortcutApiBase('https://example.test/component/example/index.html'), 'https://example.test/phone-transfer-api/v1');
});

test('install download is generic while setup sends only upload credentials directly to Shortcuts', async () => {
  const state = await newReceiver();
  const links = shortcutInstallLinks(state.binding, 'https://whatsup.streamlit.app/~/+/component/example/index.html');
  assert.equal(links.download, `https://whatsup.streamlit.app/~/+/component/example/${encodeURIComponent('发送到办公电脑 L.shortcut')}`);
  const setup = new URL(links.setup);
  assert.equal(setup.protocol, 'shortcuts:');
  assert.equal(setup.searchParams.get('name'), '发送到办公电脑 L');
  assert.equal(setup.searchParams.get('input'), 'text');
  const text = setup.searchParams.get('text');
  assert.ok(text.startsWith('suishouchuan-setup-v1:'));
  const config = JSON.parse(text.slice('suishouchuan-setup-v1:'.length));
  assert.equal(config.url, `https://whatsup.streamlit.app/~/+/phone-transfer-api/v1/upload/${state.binding.nativeRoom}/authorize`);
  assert.equal(config.authorization, `Bearer ${shortcutUploadToken(state.binding)}`);
  assert.ok(!links.setup.includes(state.shortcutReceiverToken));
  assert.ok(!links.setup.includes(state.binding.auth));
});

test('a saved local receipt retries acknowledgement without writing a duplicate file', async () => {
  const oldLocation = globalThis.location;
  const oldFetch = globalThis.fetch;
  globalThis.location = { href: 'https://example.test/component/example/index.html' };
  const state = await newReceiver(); let writes = 0; let acknowledgements = 0;
  const receipt = { name: '001_photo.HEIC', folder: 'day/batch', size: 3, sha256: 'a'.repeat(64) };
  globalThis.fetch = async (url, options) => {
    assert.equal(JSON.parse(options.body).authorization, `Bearer ${state.shortcutReceiverToken}`);
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, undefined);
    if (url.endsWith('/pending')) return Response.json({ files: [{ id: 'test-file', name: 'photo.HEIC', size: 3, sha256: receipt.sha256 }] });
    if (url.endsWith('/ack')) { acknowledgements++; assert.deepEqual(JSON.parse(options.body), { ...receipt, authorization: `Bearer ${state.shortcutReceiverToken}` }); }
    return Response.json({ ok: true });
  };
  const receiver = new ShortcutReceiver(state, { canReceive: () => true, onStatus() {}, onError(e) { throw e; }, receipt: async () => receipt, receive: async () => { writes++; } });
  try {
    await receiver.poll();
    assert.equal(writes, 0); assert.equal(acknowledgements, 1);
  } finally { receiver.stop(); globalThis.fetch = oldFetch; globalThis.location = oldLocation; }
});
