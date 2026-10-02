"""Build a self-contained, zoomable viewer without changing source image bytes."""

import base64
from html import escape
import json


_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


def build_map_viewer(
    image_bytes: bytes,
    mime_type: str,
    title: str,
    *,
    crop_box: tuple[int, int, int, int] | None = None,
) -> str:
    """Return HTML for ``st.iframe(..., height="content")``.

    Source bytes are embedded as a data URL. Only raster MIME types are accepted;
    an invalid image payload is reported by the viewer's load-error state.
    ``crop_box`` is an optional (x, y, width, height) display window in source
    pixels; the embedded source bytes remain intact.
    """
    if not isinstance(image_bytes, bytes):
        raise TypeError("image_bytes must be bytes")
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")
    if mime_type not in _IMAGE_MIME_TYPES:
        raise ValueError("Unsupported raster image MIME type")
    if crop_box is not None:
        if not isinstance(crop_box, tuple) or len(crop_box) != 4:
            raise TypeError("crop_box must be a tuple of four integers")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in crop_box):
            raise TypeError("crop_box values must be non-boolean integers")
        if crop_box[0] < 0 or crop_box[1] < 0 or crop_box[2] <= 0 or crop_box[3] <= 0:
            raise ValueError("crop_box requires non-negative x/y and positive width/height")
    source = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    return (
        _VIEWER_HTML.replace("__IMAGE_SOURCE__", source)
        .replace("__CROP_BOX__", json.dumps(crop_box))
        .replace("__MAP_TITLE__", escape(str(title), quote=True))
    )


_VIEWER_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__MAP_TITLE__</title>
<style>
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #34322e; font: 14px/1.4 system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
.viewer { border: 1px solid #e6e2db; border-radius: 12px; overflow: hidden; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 8px 10px; background: #faf9f6; border-bottom: 1px solid #e6e2db; }
button { appearance: none; background: #fff; color: #39372f; border: 1px solid #dcd7ce; border-radius: 6px; padding: 6px 10px; font: inherit; cursor: pointer; min-height: 32px; }
button:hover:not(:disabled) { background: #f0ede6; }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible, .stage:focus-visible { outline: 2px solid #987436; outline-offset: -2px; }
.scale { margin-left: auto; color: #6b665e; font-variant-numeric: tabular-nums; white-space: nowrap; }
.stage { position: relative; height: clamp(300px, 76vw, 570px); overflow: hidden; touch-action: none; background: #f0eeea; cursor: grab; }
.stage.dragging { cursor: grabbing; }
.map-layer { position: absolute; left: 0; top: 0; overflow: hidden; transform-origin: 0 0; visibility: hidden; }
.map-layer img { position: absolute; left: 0; top: 0; max-width: none; max-height: none; user-select: none; -webkit-user-drag: none; }
.message { position: absolute; inset: 0; display: grid; place-content: center; padding: 24px; text-align: center; color: #6b665e; pointer-events: none; }
.message[hidden] { display: none; }
.hint { padding: 6px 10px; color: #787168; font-size: 12px; background: #faf9f6; }
@media (max-width: 420px) { .toolbar { gap: 4px; padding: 6px; } button { padding: 6px 8px; } .hint { font-size: 11px; } }
</style>
</head>
<body>
<div class="viewer">
  <div class="toolbar" role="toolbar" aria-label="地图缩放工具">
    <button type="button" id="zoom-in" aria-label="放大地图" title="放大（+）" disabled>＋</button>
    <button type="button" id="zoom-out" aria-label="缩小地图" title="缩小（−）" disabled>−</button>
    <button type="button" id="fit" title="适应窗口（0）" disabled>适应窗口</button>
    <button type="button" id="original" title="原始尺寸（1）" disabled>原始尺寸</button>
    <span class="scale" id="scale" aria-label="当前缩放比例">加载中</span>
  </div>
  <div class="stage" id="stage" tabindex="0" role="region" aria-label="__MAP_TITLE__，可拖动及缩放" aria-describedby="hint">
    <div class="map-layer" id="map-layer">
      <img id="map" src="__IMAGE_SOURCE__" alt="__MAP_TITLE__" draggable="false">
    </div>
    <div class="message" id="message" role="status" aria-live="polite">正在加载高清地图…</div>
  </div>
  <div class="hint" id="hint">滚轮或双指缩放 · 拖动查看 · 聚焦地图后可用方向键移动，+ / − 缩放</div>
</div>
<script>
(() => {
  "use strict";
  const cropBox = __CROP_BOX__;
  const stage = document.getElementById("stage");
  const mapLayer = document.getElementById("map-layer");
  const image = document.getElementById("map");
  const message = document.getElementById("message");
  const scaleLabel = document.getElementById("scale");
  const zoomIn = document.getElementById("zoom-in");
  const zoomOut = document.getElementById("zoom-out");
  const fitButton = document.getElementById("fit");
  const originalButton = document.getElementById("original");
  const buttons = [zoomIn, zoomOut, fitButton, originalButton];
  const pointers = new Map();
  let ready = false;
  let scale = 1;
  let x = 0;
  let y = 0;
  let fitting = true;
  let contentWidth = 0;
  let contentHeight = 0;

  function fitScale() {
    return Math.min(stage.clientWidth / contentWidth, stage.clientHeight / contentHeight, 1);
  }
  function minScale() { return fitScale() / 2; }
  function clampScale(value) { return Math.min(8, Math.max(minScale(), value)); }
  function render() {
    if (!ready) return;
    const width = contentWidth * scale;
    const height = contentHeight * scale;
    x = width <= stage.clientWidth ? (stage.clientWidth - width) / 2 : Math.min(0, Math.max(stage.clientWidth - width, x));
    y = height <= stage.clientHeight ? (stage.clientHeight - height) / 2 : Math.min(0, Math.max(stage.clientHeight - height, y));
    mapLayer.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    scaleLabel.textContent = `${Math.round(scale * 100)}%`;
    zoomIn.disabled = scale >= 8;
    zoomOut.disabled = scale <= minScale();
  }
  function fit() {
    if (!ready) return;
    fitting = true;
    scale = fitScale();
    x = (stage.clientWidth - contentWidth * scale) / 2;
    y = (stage.clientHeight - contentHeight * scale) / 2;
    render();
  }
  function zoom(value, anchorX = stage.clientWidth / 2, anchorY = stage.clientHeight / 2) {
    if (!ready) return;
    fitting = false;
    const next = clampScale(value);
    x = anchorX - (anchorX - x) * next / scale;
    y = anchorY - (anchorY - y) * next / scale;
    scale = next;
    render();
  }
  function localPoint(event) {
    const rect = stage.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }
  function gesture() {
    const points = Array.from(pointers.values()).slice(0, 2);
    if (points.length === 1) return { ...points[0], distance: 0 };
    const [a, b] = points;
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, distance: Math.hypot(b.x - a.x, b.y - a.y) };
  }
  function loaded() {
    if (ready) return;
    if (!image.naturalWidth || !image.naturalHeight) { failed(); return; }
    const area = cropBox || [0, 0, image.naturalWidth, image.naturalHeight];
    const [cropX, cropY, cropWidth, cropHeight] = area;
    if (!area.every(Number.isSafeInteger) || cropX < 0 || cropY < 0 || cropWidth <= 0 || cropHeight <= 0 ||
        cropWidth > image.naturalWidth - cropX || cropHeight > image.naturalHeight - cropY) {
      failed("地图显示范围超出原图边界，请检查裁切配置。");
      return;
    }
    contentWidth = cropWidth;
    contentHeight = cropHeight;
    ready = true;
    mapLayer.style.width = `${contentWidth}px`;
    mapLayer.style.height = `${contentHeight}px`;
    image.style.width = `${image.naturalWidth}px`;
    image.style.height = `${image.naturalHeight}px`;
    image.style.left = `${-cropX}px`;
    image.style.top = `${-cropY}px`;
    mapLayer.style.visibility = "visible";
    message.hidden = true;
    buttons.forEach(button => { button.disabled = false; });
    fit();
  }
  function failed(detail = "地图未能显示，请重新选择地图或刷新页面。") {
    ready = false;
    mapLayer.style.visibility = "hidden";
    message.hidden = false;
    message.textContent = detail;
    scaleLabel.textContent = "加载失败";
    buttons.forEach(button => { button.disabled = true; });
  }
  image.addEventListener("load", loaded);
  image.addEventListener("error", () => failed());
  if (image.complete) { if (image.naturalWidth) loaded(); else failed(); }

  zoomIn.addEventListener("click", () => zoom(scale * 1.35));
  zoomOut.addEventListener("click", () => zoom(scale / 1.35));
  fitButton.addEventListener("click", fit);
  originalButton.addEventListener("click", () => zoom(1));
  stage.addEventListener("wheel", event => {
    if (!ready) return;
    event.preventDefault();
    const point = localPoint(event);
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1);
    zoom(scale * Math.exp(-Math.max(-400, Math.min(400, delta)) * .002), point.x, point.y);
  }, { passive: false });
  stage.addEventListener("pointerdown", event => {
    if (!ready || (event.pointerType === "mouse" && event.button !== 0)) return;
    stage.focus({ preventScroll: true });
    pointers.set(event.pointerId, localPoint(event));
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("dragging");
  });
  stage.addEventListener("pointermove", event => {
    if (!pointers.has(event.pointerId)) return;
    const before = gesture();
    pointers.set(event.pointerId, localPoint(event));
    const after = gesture();
    const next = before.distance > 0 && after.distance > 0 ? clampScale(scale * after.distance / before.distance) : scale;
    x = after.x - (before.x - x) * next / scale;
    y = after.y - (before.y - y) * next / scale;
    scale = next;
    fitting = false;
    render();
  });
  function release(event) {
    pointers.delete(event.pointerId);
    if (!pointers.size) stage.classList.remove("dragging");
  }
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
  stage.addEventListener("lostpointercapture", release);
  stage.addEventListener("keydown", event => {
    if (!ready) return;
    const moves = { ArrowLeft: [60, 0], ArrowRight: [-60, 0], ArrowUp: [0, 60], ArrowDown: [0, -60] };
    if (moves[event.key]) {
      fitting = false;
      x += moves[event.key][0]; y += moves[event.key][1]; render();
    } else if (event.key === "+" || event.key === "=") zoom(scale * 1.35);
    else if (event.key === "-") zoom(scale / 1.35);
    else if (event.key === "0" || event.key === "Home") fit();
    else if (event.key === "1") zoom(1);
    else return;
    event.preventDefault();
  });
  new ResizeObserver(() => {
    if (!ready) return;
    if (fitting) fit(); else { scale = clampScale(scale); render(); }
  }).observe(stage);
})();
</script>
</body>
</html>
"""
