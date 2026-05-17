"""本地 OCR — 分区域识别色卡"""
import re
import subprocess
import sys
import tempfile
import os
from PIL import Image, ImageFilter, ImageEnhance, ImageOps

IMG = r"E:\GoogleDrive\Ding2026\1.png"
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA = r"C:\Users\Administrator\tessdata"

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


img = Image.open(IMG).convert("RGB")
w, h = img.size
print(f"原图: {w}x{h}")

# 图片布局（基于之前像素扫描）：
# y  0-50:   黑色边框
# y 50-920:  深蓝主色区（上半张）
# y 920-960: 黑色分割线
# y 960+:    底部色块区

# 切割图片为多个区域，分别 OCR
regions = {
    "标题区上部": (0, 0, w, h // 4),
    "标题区中部": (0, h // 5, w, h // 3),
    "主色区下部": (0, h // 3, w, h // 2),
    "分割线附近": (0, h // 2 - 100, w, h // 2 + 200),
    "底部色块区": (0, h // 2 + 100, w, h * 3 // 4),
    "最底部":     (0, h * 3 // 4, w, h),
}

# 也尝试将整图放大 5 倍后 OCR
img5x = img.resize((w * 5, h * 5), Image.LANCZOS)
gray5 = img5x.convert("L")
enhanced = ImageEnhance.Contrast(gray5).enhance(4.0)
enhanced = enhanced.filter(ImageFilter.SHARPEN)

print("\n" + "=" * 60)
print("整图 5x 放大 + 高对比度")
print("=" * 60)
text_whole = ocr(enhanced, psm=6)
print(text_whole)

# 分区域 OCR
for name, (x1, y1, x2, y2) in regions.items():
    crop = img.crop((x1, y1, x2, y2))
    crop5x = crop.resize((crop.width * 5, crop.height * 5), Image.LANCZOS)
    gray = crop5x.convert("L")
    enh = ImageEnhance.Contrast(gray).enhance(4.0)
    enh = enh.filter(ImageFilter.SHARPEN)

    print(f"\n{'=' * 60}")
    print(f"区域: {name} ({x1},{y1})-({x2},{y2})")
    print("=" * 60)
    text = ocr(enh, psm=6)
    print(text.strip() if text.strip() else "(无识别结果)")

    # 尝试只识别英文数字
    text_eng = ocr(enh, psm=6, lang="eng")
    hexes = re.findall(r"#[0-9A-Fa-f]{6}", text_eng)
    if hexes:
        print(f"  -> 英文模式识别到色号: {hexes}")

# 汇总
print("\n" + "=" * 60)
print("汇总")
print("=" * 60)
hexes = re.findall(r"#[0-9A-Fa-f]{6}", text_whole)
print(f"色号: {hexes}")
