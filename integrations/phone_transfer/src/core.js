import { sha256 } from '@noble/hashes/sha2.js';

export const MAX_FILE = 200 * 1024 * 1024;
export const CHUNK = 512 * 1024;
export const bytes = value => value instanceof Uint8Array ? value : new Uint8Array(value);
export const hex = value => Array.from(bytes(value), b => b.toString(16).padStart(2, '0')).join('');
export const randomHex = size => hex(crypto.getRandomValues(new Uint8Array(size)));
export const b64 = value => btoa(String.fromCharCode(...bytes(value))).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
export function unb64(value) {
  if (typeof value !== 'string' || !/^[\w-]+$/.test(value) || value.length > 2000) throw new Error('绑定信息无效');
  return Uint8Array.from(atob(value.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
}
const encoder = new TextEncoder();
export function parseToken(value) {
  const raw = value.includes('#transfer=') ? value.split('#transfer=')[1] : value;
  let data;
  try { data = JSON.parse(new TextDecoder().decode(unb64(raw.trim()))); } catch { throw new Error('绑定信息不完整，请重新扫码或粘贴完整链接'); }
  if (data.v !== 1 || !/^[a-f0-9]{64}$/.test(data.room) || unb64(data.auth).length !== 32 || unb64(data.publicKey).length !== 65) throw new Error('绑定信息无效');
  if (data.nativeRoom !== undefined && !/^[a-f0-9]{64}$/.test(data.nativeRoom)) throw new Error('绑定信息无效');
  return { v: 1, room: data.room, auth: data.auth, publicKey: data.publicKey, ...(data.nativeRoom ? { nativeRoom: data.nativeRoom } : {}) };
}
export const tokenFor = binding => b64(encoder.encode(JSON.stringify(binding)));
export async function newReceiver() {
  const keys = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign', 'verify']);
  const shortcutReceiverToken = randomHex(32);
  return { role: 'receiver', shortcutReceiverToken, privateKey: keys.privateKey, binding: { v: 1, room: randomHex(32), nativeRoom: hex(sha256(encoder.encode(shortcutReceiverToken))), auth: b64(crypto.getRandomValues(new Uint8Array(32))), publicKey: b64(await crypto.subtle.exportKey('raw', keys.publicKey)) } };
}
export function proofText(room, receiverNonce, senderNonce, connectionIds) {
  return encoder.encode(JSON.stringify([room, receiverNonce, senderNonce, [...connectionIds].sort()]));
}
function roleProofText(role, transcript) {
  if (!['receiver', 'sender'].includes(role)) throw new Error('无效的设备角色');
  const prefix = encoder.encode(`suishou-proof-v1:${role}\0`);
  const result = new Uint8Array(prefix.length + transcript.length);
  result.set(prefix); result.set(transcript, prefix.length); return result;
}
export async function makeProof(state, transcript) {
  const payload = roleProofText(state.role, transcript);
  const key = await crypto.subtle.importKey('raw', unb64(state.binding.auth), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const proof = { mac: b64(await crypto.subtle.sign('HMAC', key, payload)) };
  if (state.role === 'receiver') proof.signature = b64(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, state.privateKey, payload));
  return proof;
}
export async function verifyProof(binding, remoteRole, transcript, proof) {
  try {
    const payload = roleProofText(remoteRole, transcript);
    const key = await crypto.subtle.importKey('raw', unb64(binding.auth), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
    if (!await crypto.subtle.verify('HMAC', key, unb64(proof.mac), payload)) return false;
    if (remoteRole === 'receiver') {
      const publicKey = await crypto.subtle.importKey('raw', unb64(binding.publicKey), { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
      return crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, publicKey, unb64(proof.signature), payload);
    }
    return remoteRole === 'sender';
  } catch { return false; }
}
export function dateParts(now = new Date()) {
  const pad = n => String(n).padStart(2, '0');
  return { day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`, time: `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}` };
}
export function safeFilename(name) {
  let clean = String(name).normalize('NFC').replace(/[<>:"/\\|?*\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, '_').replace(/[. ]+$/, '');
  if (clean.length > 130) {
    const extension = clean.match(/\.[a-zA-Z0-9]{1,16}$/)?.[0] || '';
    clean = clean.slice(0, 130 - extension.length).replace(/[. ]+$/, '') + extension;
  }
  if (!clean || /^\.+$/.test(clean)) clean = '文件';
  if (/^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(clean)) clean = `_${clean}`;
  return clean;
}
export function validateFiles(files) {
  if (!Array.isArray(files) || !files.length || files.length > 500) throw new Error('每次请选择 1–500 个文件');
  return files.map(f => {
    if (typeof f.name !== 'string' || !f.name.length || f.name.length > 1024 || !Number.isSafeInteger(f.size) || f.size < 0 || f.size > MAX_FILE) throw new Error('单个文件不能超过 200 MiB，文件信息必须完整');
    return { name: f.name, size: f.size, lastModified: Number.isFinite(f.lastModified) ? f.lastModified : 0 };
  });
}
export async function fileDigest(file) {
  const hash = sha256.create();
  const reader = file.stream().getReader();
  try { for (;;) { const { done, value } = await reader.read(); if (done) break; hash.update(value); } } finally { reader.releaseLock(); }
  return hex(hash.digest());
}
export async function exists(directory, name, kind = 'file') {
  try { await directory[kind === 'file' ? 'getFileHandle' : 'getDirectoryHandle'](name); return true; }
  catch (e) { if (e.name === 'NotFoundError') return false; if (e.name === 'TypeMismatchError') return true; throw e; }
}
export class IncomingTransfer {
  constructor(root, onSaved = () => {}) { this.root = root; this.onSaved = onSaved; this.active = null; this.batch = null; this.closed = false; }
  async begin(files) {
    if (this.batch || this.closed) throw new Error('已有传输正在进行');
    const manifest = validateFiles(files);
    const { day, time } = dateParts();
    const dayDir = await this.root.getDirectoryHandle(day, { create: true });
    // A fresh random directory per batch plus one writer prevents filename races
    // between retries, duplicate source names, and other receiving tabs.
    let name;
    for (let attempt = 0; attempt < 8; attempt++) {
      name = `${time}_${randomHex(16)}`;
      if (!await exists(dayDir, name, 'directory')) break;
      name = null;
    }
    if (!name) throw new Error('无法创建独立保存目录');
    const directory = await dayDir.getDirectoryHandle(name, { create: true });
    this.batch = { manifest, directory, folder: `${day}/${name}`, index: 0, saved: [] };
    return this.batch.folder;
  }
  async start(index) {
    const batch = this.batch;
    if (this.closed || !batch || this.active || index !== batch.index || !batch.manifest[index]) throw new Error('文件顺序不正确');
    const source = batch.manifest[index];
    let name = `${String(index + 1).padStart(3, '0')}_${safeFilename(source.name)}`;
    for (let i = 0; await exists(batch.directory, name); i++) {
      if (i >= 8) throw new Error('文件名冲突，未覆盖现有文件');
      name = `${String(index + 1).padStart(3, '0')}_${randomHex(8)}_${safeFilename(source.name)}`;
    }
    const handle = await batch.directory.getFileHandle(name, { create: true });
    if ((await handle.getFile()).size !== 0) throw new Error('目标文件已存在，已停止以免覆盖');
    const writer = await handle.createWritable({ keepExistingData: false, mode: 'exclusive' });
    this.active = { source, name, handle, writer, received: 0, hash: sha256.create() };
  }
  async write(chunk) {
    const a = this.active;
    const part = bytes(chunk);
    if (this.closed || !a || !part.length || part.length > CHUNK || a.received + part.length > a.source.size) throw new Error('接收到的文件大小不符合清单');
    await a.writer.write(part);
    a.hash.update(part); a.received += part.length;
    return a.received;
  }
  async finish(index, expectedHash) {
    const a = this.active;
    if (this.closed || !a || index !== this.batch.index || a.received !== a.source.size || !/^[a-f0-9]{64}$/.test(expectedHash) || hex(a.hash.digest()) !== expectedHash) throw new Error('内容校验失败，未报告送达');
    await a.writer.close();
    a.writer = null;
    const savedFile = await a.handle.getFile();
    if (savedFile.size !== a.source.size || await fileDigest(savedFile) !== expectedHash) throw new Error('落盘后校验失败，未报告送达');
    const result = { name: a.name, size: savedFile.size, sha256: expectedHash, folder: this.batch.folder };
    this.batch.saved.push(result); this.batch.index++; this.active = null;
    this.onSaved(result);
    return result;
  }
  complete() {
    if (this.closed || !this.batch || this.active || this.batch.index !== this.batch.manifest.length) throw new Error('仍有文件未完整保存');
    const results = this.batch.saved; this.batch = null; return results;
  }
  async abort() {
    this.closed = true;
    const active = this.active; this.active = null; this.batch = null;
    if (active?.writer) { try { await active.writer.abort(); } catch { /* A disconnected writer may already be closed. */ } }
    // Never remove an existing file; an interrupted newly-created placeholder
    // may remain empty and is never included in the saved-file receipt.
  }
}
export { sha256 };
