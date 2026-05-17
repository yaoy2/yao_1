"""通过浏览器 CDP 下载微信文章 8 张大图"""
import subprocess
import json
import base64
import sys
import os

TARGET = "5FAE32AEF56335BAA1060DE2D507E977"
OUT_DIR = r"E:\ai_1\github\thebeginning\exports\color_cards"
os.makedirs(OUT_DIR, exist_ok=True)

sys.stdout.reconfigure(encoding="utf-8")

# 获取 8 张图的 src URL
js_get_urls = '''
JSON.stringify(
  Array.from(document.querySelectorAll("img"))
    .filter(img => img.naturalWidth === 1441 && img.naturalHeight === 1921)
    .slice(0, 8)
    .map((img, i) => ({i, src: img.src}))
)
'''

result = subprocess.run(
    ["curl", "-s", "-X", "POST",
     f"http://localhost:3456/eval?target={TARGET}",
     "-d", js_get_urls],
    capture_output=True, text=True
)
data = json.loads(json.loads(result.stdout)["value"])
print(f"找到 {len(data)} 张图")

for item in data:
    idx = item["i"]
    src = item["src"]
    print(f"\n下载第 {idx+1} 张...")

    # 通过浏览器 fetch 图片并转 base64，分块返回
    js_fetch = f'''
    (async () => {{
      const resp = await fetch("{src}");
      const blob = await resp.blob();
      return await new Promise(r => {{
        const reader = new FileReader();
        reader.onload = () => r(reader.result.split(",")[1]);
        reader.readAsDataURL(blob);
      }});
    }})()
    '''
    result = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"http://localhost:3456/eval?target={TARGET}",
         "-d", js_fetch],
        capture_output=True, text=True, timeout=30
    )
    b64_data = json.loads(result.stdout)["value"]
    img_bytes = base64.b64decode(b64_data)
    out_path = os.path.join(OUT_DIR, f"card{idx+1}.png")
    with open(out_path, "wb") as f:
        f.write(img_bytes)
    print(f"  保存: {out_path} ({len(img_bytes)} bytes)")

print("\n全部下载完成")
