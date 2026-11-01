"""Build a local portable Windows executable; no installation or publication."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.file_distribution.rules import ENTRY_FILENAME, USER_GUIDE, VERSION


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "m20-file-distribution")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows可执行程序必须在Windows上构建。")
    work = ROOT / ".tmp" / "m20-pyinstaller"
    work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--noupx",
        "--name", Path(ENTRY_FILENAME).stem, "--paths", str(ROOT),
        "--distpath", str(args.output), "--workpath", str(work / "work"), "--specpath", str(work),
        str(ROOT / "scripts" / "file_distribution.py"),
    ], cwd=ROOT, check=True)
    executable = args.output / ENTRY_FILENAME
    sources = [*sorted((ROOT / "integrations" / "file_distribution").glob("*.py")), ROOT / "scripts" / "file_distribution.py"]
    source_hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    manifest = {
        "version": VERSION, "entry": ENTRY_FILENAME,
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "source_files": source_hashes,
    }
    (args.output / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "使用说明.txt").write_text(f"M20 文件分发 {VERSION}\n\n{USER_GUIDE}", encoding="utf-8")
    # Keep the existing user-facing shortcut on the same implementation.
    legacy_entry = ROOT / "integrations" / "file_distribution" / "legacy_entry.bat"
    (args.output / "文件分发-纪要_考勤_新闻.bat").write_text(
        legacy_entry.read_text(encoding="utf-8"), encoding="utf-8", newline="\r\n",
    )
    print(json.dumps({"executable": str(executable), "bytes": executable.stat().st_size, "sha256": manifest["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
