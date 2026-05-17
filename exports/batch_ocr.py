"""批量 OCR 8 张色卡"""
import re
import subprocess
import sys
import tempfile
import os
import json
from PIL import Image, ImageFilter, ImageEnhance

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA = r"C:\Users\Administrator\tessdata"
CARD_DIR = r"E:\ai_1\github\thebeginning\exports\color_cards"

sys.stdout.reconfigure(encoding="utf-8")


def ocr(img, psm=6, lang="chi_sim+eng"):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img.save(tf.name)
        tmp = tf.name
    result = subprocess.run(
        [TESS, tmp, "stdout", "--tessdata-dir", TESSDATA,
         "-l", lang, "--psm", str(psm), "--oem", "3"],
        capture_output=True, text=True, encoding="utf-8"
    )
    os.unlink(tmp)
    return result.stdout


def process_card(path, card_num):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    results = {"card": card_num, "name": "", "colors": []}

    # === 整图 5x OCR ===
    img5x = img.resize((w * 5, h * 5), Image.LANCZOS)
    gray5 = img5x.convert("L")
    enhanced = ImageEnhance.Contrast(gray5).enhance(4.0)
    enhanced = enhanced.filter(ImageFilter.SHARPEN)

    text_whole = ocr(enhanced, psm=6)
    hexes = re.findall(r"#[0-9A-Fa-f]{6}", text_whole)
    if hexes:
        results["colors"].extend(hexes)

    # === 分区域 OCR（底部色块区更清晰） ===
    # 大致区域：上 1/3 标题，中间主色，下 1/3 色块
    for y_start_frac, y_end_frac, label in [
        (0.3, 0.5, "主色区"),
        (0.5, 0.65, "中间区"),
        (0.65, 0.85, "色块区"),
        (0.85, 1.0, "底部区"),
    ]:
        y1 = int(h * y_start_frac)
        y2 = int(h * y_end_frac)
        crop = img.crop((0, y1, w, y2))
        crop5x = crop.resize((crop.width * 5, crop.height * 5), Image.LANCZOS)
        gray = crop5x.convert("L")
        enh = ImageEnhance.Contrast(gray).enhance(4.0)
        enh = enh.filter(ImageFilter.SHARPEN)

        text_chi = ocr(enh, psm=6, lang="chi_sim+eng")
        text_eng = ocr(enh, psm=6, lang="eng")

        region_hexes = re.findall(r"#[0-9A-Fa-f]{6}", text_chi + "\n" + text_eng)
        results["colors"].extend(region_hexes)

        # 提取中文名（括号内内容通常是方案名）
        if not results["name"]:
            name_m = re.search(r"[（(](.+?)[）)]", text_chi)
            if name_m:
                results["name"] = name_m.group(1).strip()

    # 去重保序
    seen = set()
    unique = []
    for h_code in results["colors"]:
        if h_code not in seen:
            seen.add(h_code)
            unique.append(h_code)
    results["colors"] = unique

    return results


# 处理全部 8 张
all_results = []
for i in range(1, 9):
    path = os.path.join(CARD_DIR, f"card{i}.png")
    if not os.path.exists(path):
        print(f"Card {i}: 文件不存在")
        continue
    print(f"\n{'='*60}")
    print(f"Card {i}: {path}")
    print(f"{'='*60}")
    r = process_card(path, i)
    all_results.append(r)
    print(f"  方案名: {r['name']}")
    print(f"  色号: {r['colors']}")

# 汇总输出
print(f"\n{'='*60}")
print("汇总结果")
print(f"{'='*60}")
for r in all_results:
    print(f"Card {r['card']}: {r['name']} | {', '.join(r['colors'])}")

# 保存 JSON
out = os.path.join(CARD_DIR, "ocr_results.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"\n结果保存: {out}")
