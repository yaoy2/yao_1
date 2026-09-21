import { hex, sha256 } from './core.js';

const encoder = new TextEncoder();
export function shortcutUploadToken(binding) {
  return hex(sha256(encoder.encode(`suishou-shortcut-upload-v1:${binding.room}:${binding.auth}`)));
}
export function shortcutApiBase(url = location.href) {
  const current = new URL(url);
  // Community Cloud's outer page is a shell. Its /~/+/ path forwards requests
  // to the actual app, including native Shortcut requests without a browser.
  return new URL(`${current.pathname.startsWith('/~/+/') ? '/~/+' : ''}/phone-transfer-api/v1`, current.origin).href;
}
export function shortcutConfig(binding) {
  if (!binding.nativeRoom) throw new Error('请在 L 点“绑定手机”，重新扫码以启用相册分享。');
  return { url: `${shortcutApiBase()}/upload/${binding.nativeRoom}/authorize`, authorization: `Bearer ${shortcutUploadToken(binding)}` };
}

export class ShortcutReceiver {
  constructor(state, callbacks) {
    this.state = state; this.callbacks = callbacks; this.stopped = false; this.failures = new Set(); this.polling = false;
    this.base = `${shortcutApiBase()}/receivers/${state.binding.nativeRoom}`;
  }
  async request(path, options = {}) {
    // Community Cloud strips custom headers and Authorization. Keep credentials
    // in the HTTPS request body, never in persistent URLs or query strings.
    const body = { ...JSON.parse(options.body || '{}'), authorization: `Bearer ${this.state.shortcutReceiverToken}` };
    const response = await fetch(this.base + path, { cache: 'no-store', signal: this.controller.signal, ...options, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) {
      throw new Error(response.status === 404 ? '相册分享服务正在更新，请稍后重新打开接收页' : '相册分享服务暂不可用，请保持接收页打开');
    }
    return response;
  }
  async register() {
    const uploadToken = shortcutUploadToken(this.state.binding);
    await this.request('', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ upload_token_hash: hex(sha256(encoder.encode(uploadToken))) }) });
  }
  start() {
    this.failures.clear();
    if (!this.polling) this.poll();
  }
  async poll() {
    if (this.stopped || this.polling) return;
    this.polling = true; this.controller = new AbortController();
    // Registration is a heartbeat. The separate read token never goes to phones.
    const deadline = setTimeout(() => this.controller.abort(), 20000); let heartbeat;
    try {
      await this.register();
      const pending = await (await this.request('/pending')).json();
      clearTimeout(deadline);
      heartbeat = setInterval(() => { if (!this.stopped) this.register().catch(() => {}); }, 10000);
      this.callbacks.onStatus('相册分享已就绪');
      for (const file of pending.files) {
        if (this.stopped || !this.callbacks.canReceive()) break;
        if (this.failures.has(file.id)) continue;
        try {
          const previous = await this.callbacks.receipt(file.id);
          const result = previous || await this.callbacks.receive(file, async () => {
            const response = await fetch(`${this.base}/files/${file.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ authorization: `Bearer ${this.state.shortcutReceiverToken}` }), cache: 'no-store', signal: this.controller.signal });
            if (!response.ok || !response.body) throw new Error('照片下载中断，尚未确认保存');
            return response.body;
          });
          if (!previous) await this.callbacks.receipt(file.id, result);
          await this.request(`/files/${file.id}/ack`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result) });
        } catch (error) {
          if (!this.stopped) { this.failures.add(file.id); this.callbacks.onError(error); }
        }
      }
    } catch (error) {
      if (!this.stopped) this.callbacks.onStatus(error.name === 'AbortError' ? '相册分享连接超时，正在重连' : error.message);
    } finally {
      clearTimeout(deadline); clearInterval(heartbeat); this.polling = false;
      if (!this.stopped) this.timer = setTimeout(() => this.poll(), 1500);
    }
  }
  stop() { this.stopped = true; clearTimeout(this.timer); this.controller?.abort(); }
}
