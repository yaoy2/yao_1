"""批量 OCR v2 — 针对性预处理"""
import re
import subprocess
import sys
import tempfile
import os
import json
from PIL import Image, ImageFilter, ImageEnhance, ImageOps

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


def preprocess_variants(img):
    """对一张图生成多种预处理变体"""
    variants = []
    # 放大
    for scale in [4, 6, 8]:
        big = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
        gray = big.convert("L")
        # 标准增强
        enh = ImageEnhance.Contrast(gray).enhance(4.0)
        enh = enh.filter(ImageFilter.SHARPEN)
        variants.append((f"scale{scale}_contrast", enh))
        # 反色（白字在深色背景上）
        inv = ImageOps.invert(gray)
        inv = ImageEnhance.Contrast(inv).enhance(4.0)
        inv = inv.filter(ImageFilter.SHARPEN)
        variants.append((f"scale{scale}_inverted", inv))
    return variants


def ocr_all_variants(img, lang="chi_sim+eng"):
    """用多种预处理变体 OCR，汇总结果"""
    all_text = ""
    variants = preprocess_variants(img)
    for name, vimg in variants:
        text = ocr(vimg, psm=6, lang=lang)
        if text.strip():
            all_text += f"\n--- {name} ---\n{text}"
    return all_text


def process_card(path, card_num):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    all_text = ""

    # 1. 整图 OCR
    all_text += ocr_all_variants(img)

    # 2. 分区域：重点是底部 1/3（色号和名称所在区域）
    # 根据 card1 的已知布局，色号在 y=75%~100% 区域
    for frac_start, frac_end in [(0.0, 0.15), (0.15, 0.35), (0.35, 0.55),
                                  (0.55, 0.7), (0.7, 0.85), (0.85, 1.0)]:
        y1 = int(h * frac_start)
        y2 = int(h * frac_end)
        crop = img.crop((0, y1, w, y2))
        # 用 8x 放大
        big = crop.resize((crop.width * 8, crop.height * 8), Image.LANCZOS)
        gray = big.convert("L")
        # 尝试标准和反色
        for prefix, proc in [
            ("std", lambda g: ImageEnhance.Contrast(g).enhance(5.0).filter(ImageFilter.SHARPEN)),
            ("inv", lambda g: ImageEnhance.Contrast(ImageOps.invert(g)).enhance(5.0).filter(ImageFilter.SHARPEN)),
        ]:
            processed = proc(gray)
            text = ocr(processed, psm=6, lang="chi_sim+eng")
            text_eng = ocr(processed, psm=6, lang="eng")
            all_text += f"\n[{frac_start:.0%}-{frac_end:.0%} {prefix}]\n{text}\n{text_eng}"

    # 提取色号
    hex_codes = re.findall(r"#[0-9A-Fa-f]{6}", all_text)
    # 去重保序
    seen = set()
    unique_hex = []
    for h in hex_codes:
        if h not in seen:
            seen.add(h)
            unique_hex.append(h)

    # 提取方案名（括号内容）
    name = ""
    name_matches = re.findall(r"[（(]\s*(.+?)\s*[）)]", all_text)
    for nm in name_matches:
        # 过滤掉太短或明显不是中文名的
        clean = re.sub(r"\s+", "", nm)
        if len(clean) >= 2 and re.search(r"[一-鿿]", clean):
            name = clean
            break

    # 提取中文颜色名（在色号附近出现的中文）
    color_names = {}
    for line in all_text.split("\n"):
        for hex_c in unique_hex:
            if hex_c in line:
                # 提取色号前后的中文
                parts = line.split(hex_c)
                for p in parts:
                    cn = re.findall(r"[一-鿿]{2,6}", p)
                    for c in cn:
                        if c not in ("配色灵感", "审美提升", "好看", "高级感", "高级", "感配"):
                            color_names[hex_c] = c

    return {
        "card": card_num,
        "name": name,
        "colors": unique_hex,
        "color_names": color_names,
        "raw_text": all_text[:3000]
    }


# 处理全部 8 张
all_results = []
for i in range(1, 9):
    path = os.path.join(CARD_DIR, f"card{i}.png")
    if not os.path.exists(path):
        print(f"Card {i}: 文件不存在")
        continue
    print(f"\n{'='*60}")
    print(f"Card {i}")
    print(f"{'='*60}")
    r = process_card(path, i)
    all_results.append(r)
    print(f"  方案名: {r['name']}")
    print(f"  色号: {r['colors']}")
    print(f"  颜色名: {r['color_names']}")

# 保存
out = os.path.join(CARD_DIR, "ocr_results_v2.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print("汇总")
print(f"{'='*60}")
for r in all_results:
    print(f"Card {r['card']}: [{r['name']}] {', '.join(r['colors'])}")
    for hc, cn in r["color_names"].items():
        print(f"  {hc} -> {cn}")
