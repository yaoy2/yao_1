import { bytes, hex, randomHex, sha256, unb64 } from './core.js';

const encoder = new TextEncoder(), decoder = new TextDecoder();
function encode64(data) {
  let text = '';
  for (let i = 0; i < data.length; i += 16384) text += String.fromCharCode(...data.subarray(i, i + 16384));
  return btoa(text).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
function decode64(text) {
  if (typeof text !== 'string' || text.length > 1500000 || !/^[\w-]+$/.test(text)) throw new Error('加密分块无效');
  return Uint8Array.from(atob(text.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
}

// Separate routing authorization from the encryption secret: Python sees only
// this one-way digest, routing IDs, and ciphertext, never the pairing secret.
export const relayKey = binding => hex(sha256(encoder.encode(`suishou-routing-v1:${binding.room}:${binding.auth}`)));
export class Cipher {
  constructor(binding, source, destination) {
    this.sendSequence = 0; this.receiveSequence = 0;
    this.context = encoder.encode(JSON.stringify(['suishou-envelope-v1', binding.room, source, destination]));
    this.key = crypto.subtle.importKey('raw', unb64(binding.auth), 'HKDF', false, ['deriveKey']).then(key => crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: encoder.encode(binding.room), info: this.context }, key, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']));
  }
  async encrypt(value) {
    const data = typeof value === 'string' ? encoder.encode(value) : bytes(value);
    if (data.length > 1024 * 1024) throw new Error('传输分块过大');
    const plain = new Uint8Array(data.length + 1); plain[0] = typeof value === 'string' ? 1 : 0; plain.set(data, 1);
    const header = new Uint8Array(20); new DataView(header.buffer).setBigUint64(0, BigInt(++this.sendSequence));
    header.set(crypto.getRandomValues(new Uint8Array(12)), 8);
    const additionalData = new Uint8Array(this.context.length + header.length); additionalData.set(this.context); additionalData.set(header, this.context.length);
    const encrypted = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: header.subarray(8), additionalData }, await this.key, plain));
    const packet = new Uint8Array(header.length + encrypted.length); packet.set(header); packet.set(encrypted, header.length); return encode64(packet);
  }
  async decrypt(body) {
    const packet = decode64(body);
    if (packet.length < 37) throw new Error('加密分块不完整');
    const sequence = new DataView(packet.buffer).getBigUint64(0);
    if (sequence !== BigInt(this.receiveSequence + 1)) throw new Error('传输分块顺序不正确，请重发未完成文件');
    const header = packet.subarray(0, 20), additionalData = new Uint8Array(this.context.length + 20);
    additionalData.set(this.context); additionalData.set(header, this.context.length);
    const plain = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: header.subarray(8), additionalData }, await this.key, packet.subarray(20)));
    if (plain[0] > 1) throw new Error('无法识别加密分块');
    this.receiveSequence++; return plain[0] === 1 ? decoder.decode(plain.subarray(1)) : plain.slice(1).buffer;
  }
}

class RelayChannel extends EventTarget {
  constructor(relay, id) {
    super(); this.relay = relay; this.id = id; this.readyState = 'open'; this.bufferedAmount = 0;
    this.encryptor = new Cipher(relay.binding, relay.id, id); this.decryptor = new Cipher(relay.binding, id, relay.id); this.sending = Promise.resolve();
  }
  send(value) {
    if (this.readyState !== 'open') throw new Error('连接已断开');
    const length = typeof value === 'string' ? encoder.encode(value).length : value.byteLength;
    this.bufferedAmount += length;
    this.sending = this.sending.then(async () => {
      const body = await this.encryptor.encrypt(value);
      if (this.readyState === 'open') this.relay.enqueue({ id: randomHex(16), to: this.id, body }, this, length);
    }).catch(() => this.onerror?.());
  }
  async receive(body) {
    if (this.readyState === 'open') this.onmessage?.({ data: await this.decryptor.decrypt(body) });
  }
  accepted(length) {
    this.bufferedAmount -= length;
    if (this.bufferedAmount <= (this.bufferedAmountLowThreshold || 0)) this.dispatchEvent(new Event('bufferedamountlow'));
  }
  close() {
    if (this.readyState === 'closed') return;
    this.readyState = 'closed'; this.relay.drop(this.id); this.dispatchEvent(new Event('close')); this.onclose?.();
  }
}

export class StreamlitRelay {
  constructor(state, { onPeer, onStatus, onError }) {
    this.binding = state.binding; this.role = state.role; this.id = randomHex(16); this.key = relayKey(state.binding);
    this.onPeer = onPeer; this.onStatus = onStatus; this.onError = onError;
    this.channels = new Map(); this.outbox = []; this.ack = 0; this.serial = 0; this.closed = false;
    this.lastResponse = Date.now(); this.receiving = Promise.resolve(); this.pump();
  }
  enqueue(packet, channel, length) {
    this.outbox.push({ packet, channel, length });
    if (!this.pending) { clearTimeout(this.timer); this.pump(); }
  }
  drop(id) {
    this.channels.delete(id); this.outbox = this.outbox.filter(item => item.packet.to !== id);
  }
  pump() {
    if (this.closed || this.pending || this.processing) return;
    if (Date.now() - this.lastResponse > 45000) { this.onError(new Error('网页连接中断，请重新打开接收页；已保存文件保留')); return; }
    // At most 1 MiB plaintext per request; Python bounds total queued ciphertext.
    let size = 0;
    const packets = this.outbox.slice(0, 16).filter(item => { size += item.packet.body.length; return size <= 1800000; }).map(item => item.packet);
    const request = { room: this.binding.room, relay_key: this.key, client_id: this.id, role: this.role, ack: this.ack, packets, request_id: `${this.id}:${++this.serial}` };
    this.pending = request.request_id;
    window.parent.postMessage({ isStreamlitMessage: true, type: 'streamlit:setComponentValue', dataType: 'json', value: request }, '*');
    this.timer = setTimeout(() => { this.pending = null; this.pump(); }, 5000);
  }
  render(args) {
    if (this.closed || !this.pending || args?.request_id !== this.pending) return;
    // Ignore duplicate fragment renders while this response is being decrypted.
    this.pending = null; this.processing = true; clearTimeout(this.timer);
    this.receiving = this.receiving.then(async () => {
      const result = args.relay;
      this.lastResponse = Date.now();
      if (!result?.ok) {
        this.onStatus(false);
        if (['receiver_offline', 'receiver_busy'].includes(result?.error)) return;
        throw new Error('传输服务暂时无法接收，请稍后重新打开页面');
      }
      this.onStatus(true);
      const accepted = new Set(result.accepted);
      this.outbox = this.outbox.filter(item => { if (!accepted.has(item.packet.id)) return true; item.channel.accepted(item.length); return false; });
      const present = new Set(result.peers.map(peer => peer.id));
      for (const [id, channel] of this.channels) if (!present.has(id)) channel.close();
      for (const peer of result.peers) {
        if (peer.role === this.role || this.channels.has(peer.id)) continue;
        const channel = new RelayChannel(this, peer.id); this.channels.set(peer.id, channel); this.onPeer(peer.id, channel, this.id);
      }
      for (const msg of result.messages) {
        if (msg.id <= this.ack) continue;
        const channel = this.channels.get(msg.source);
        if (channel) await channel.receive(msg.body);
        this.ack = msg.id;
      }
    }).catch(error => this.onError(error)).finally(() => {
      this.processing = false;
      if (!this.closed && !this.pending) this.timer = setTimeout(() => this.pump(), this.outbox.length ? 0 : 300);
    });
  }
  close() {
    this.closed = true; clearTimeout(this.timer);
    window.parent.postMessage({ isStreamlitMessage: true, type: 'streamlit:setComponentValue', dataType: 'json', value: { room: this.binding.room, relay_key: this.key, client_id: this.id, role: this.role, ack: this.ack, packets: [], leave: true, request_id: `${this.id}:leave` } }, '*');
    for (const channel of [...this.channels.values()]) channel.close();
    this.outbox = [];
  }
}
