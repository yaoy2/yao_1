"""Build M29's pinned, attributed reading corpus from an upstream checkout.

No network calls or upstream code execution. The PDF and skill are copied intact;
PDF bookmarks must match every source entry before a snapshot can be published.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata

from pypdf import PdfReader


UPSTREAM = "https://github.com/eternity4719/HowToLiveBetter"
COST_WEIGHTS = {
    "money": {"0": 0, "少": 1, "多": 2},
    "time": {"少": 0, "中": 1, "多": 2},
    "will": {"否": 0, "些": 1, "是": 2},
}
FIELD_NAMES = {"成本": "cost", "说人话": "human", "收益": "gain",
               "证据等级": "grade", "来源": "src", "备注": "note"}
TAG_NAMES = {"钱": "money", "时间": "time", "毅力": "will",
             "收益": "level", "口径": "lens"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparable_title(text: str) -> str:
    # PDF layout removes Markdown emphasis and inserts line-breaking spaces.
    return "".join(ch for ch in unicodedata.normalize("NFKC", text)
                   if ch.isalnum())


def cost_ratio(level: str, score: int) -> str:
    """Same bins as upstream index.html; this is the author's C-grade judgment."""
    if level == "大":
        return "极高" if score == 0 else "高" if score <= 2 else "一般"
    return "高" if level == "中" and score == 0 else "一般"


def source_link(commit: str, path: str) -> str:
    from urllib.parse import quote
    return f"{UPSTREAM}/blob/{commit}/{quote(path, safe='/')}"


def parse_section(text: str, path: str, commit: str) -> tuple[dict, list[dict]]:
    heading = re.search(r"^# (\d+)\. (.+)$", text, re.M)
    if not heading:
        raise ValueError(f"Missing section heading: {path}")
    section_number, title = int(heading[1]), heading[2].strip()
    starts = list(re.finditer(r"^### (\d+)\. (.+)$", text, re.M))
    if not starts:
        raise ValueError(f"Empty section: {path}")
    section = {"n": section_number, "title": title,
               "intro": text[heading.end():starts[0].start()].strip(),
               "source_path": path, "source_url": source_link(commit, path),
               "question": "", "entry_count": len(starts)}
    entries = []
    for i, start in enumerate(starts):
        raw = text[start.start():starts[i+1].start() if i+1 < len(starts) else len(text)].strip()
        entry = {"id": f"s{section_number}-e{int(start[1])}", "sec": section_number,
                 "n": int(start[1]), "title": start[2].strip(), "raw": raw,
                 "source_path": path, "source_line": text[:start.start()].count("\n")+1}
        entry["source_url"] = f"{source_link(commit, path)}#L{entry['source_line']}"
        labels = re.search(r"<!--\s*成本标签:\s*(.*?)\s*-->", raw)
        if not labels:
            raise ValueError(f"Missing tags: {entry['id']}")
        for name, value in re.findall(r"(\S+)=(\S+)", labels[1]):
            if name in TAG_NAMES:
                entry[TAG_NAMES[name]] = value
        fields = list(re.finditer(r"^- (成本|说人话|收益|证据等级|来源|备注)：(.*)$", raw, re.M))
        for j, field in enumerate(fields):
            # Keep every continuation paragraph, source, qualification and date.
            end = fields[j+1].start() if j+1 < len(fields) else len(raw)
            entry[FIELD_NAMES[field[1]]] = raw[field.start()+len(field[1])+3:end].strip()
        missing = set(FIELD_NAMES.values()) - entry.keys()
        if missing:
            raise ValueError(f"Incomplete entry {entry['id']}: {missing}")
        grade = re.match(r"([ABC])\b", entry["grade"])
        if not grade:
            raise ValueError(f"Unrecognized grade: {entry['id']}")
        entry["grade_text"] = entry["grade"]
        entry["grade"] = grade[1]
        entry["cs"] = sum(weights[entry[name]] for name, weights in COST_WEIGHTS.items())
        if entry["level"] not in {"大", "中", "小"} or entry["lens"] not in {"死亡率", "金钱", "时间", "自由"}:
            raise ValueError(f"Unknown cost labels: {entry['id']}")
        entry["ratio"] = cost_ratio(entry["level"], entry["cs"])
        entry["dispute"] = entry["note"].startswith("争议")
        entry["todo"] = bool(re.search(r"待核实|TODO", "".join(entry[k] for k in ("src", "gain", "note", "cost"))))
        entries.append(entry)
    if len({e["id"] for e in entries}) != len(entries):
        raise ValueError(f"Duplicate entry ID: {path}")
    return section, entries


def pdf_locations(reader: PdfReader) -> tuple[dict, dict, dict]:
    sections, entries, documents = {}, {}, {}
    active_section = None
    for item in reader.outline:
        if isinstance(item, list):
            if active_section is None:
                continue
            def walk(children):
                for child in children:
                    if isinstance(child, list):
                        yield from walk(child)
                    else:
                        yield child
            for child in walk(item):
                match = re.match(r"^(\d+)\.\s+(.+)$", child.title)
                if match:
                    identity = f"s{active_section}-e{int(match[1])}"
                    if identity in entries:
                        raise ValueError(f"Duplicate PDF bookmark: {identity}")
                    entries[identity] = {"title": match[2], "page": reader.get_destination_page_number(child)+1}
        else:
            match = re.match(r"^(\d+)\.\s+(.+)$", item.title)
            active_section = int(match[1]) if match else None
            location = {"title": match[2] if match else item.title,
                        "page": reader.get_destination_page_number(item)+1}
            if active_section is not None:
                sections[active_section] = location
            else:
                documents[comparable_title(item.title)] = location
    return sections, entries, documents


def build_snapshot(source_dir: Path, pdf: Path, commit: str, snapshot_at: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Use the full upstream commit SHA")
    readme = (source_dir / "README.md").read_text(encoding="utf-8")
    algorithm = (source_dir / "index.html").read_text(encoding="utf-8")
    # Refuse silently carrying forward an old algorithm after an upstream edit.
    for expected in ("money:{'0':0,'少':1,'多':2}", "time:{'少':0,'中':1,'多':2}",
                     "will:{'否':0,'些':1,'是':2}",
                     "e.level === '大' ? (e.cs === 0 ? '极高' : (e.cs <= 2 ? '高' : '一般'))",
                     "e.level === '中' ? (e.cs === 0 ? '高' : '一般') : '一般'"):
        if expected not in algorithm:
            raise ValueError("Upstream cost algorithm changed; review it before building")
    files = sorted(set(re.findall(r"\]\((book/[^)]+\.md)\)", readme)))
    sections, entries = [], []
    for path in files:
        section, section_entries = parse_section((source_dir / path).read_text(encoding="utf-8"), path, commit)
        for line in readme.splitlines():
            if line.startswith("|") and f"]({path})" in line:
                section["question"] = line.strip("|").split("|")[0].strip()
                break
        sections.append(section)
        entries.extend(section_entries)
    reader = PdfReader(pdf)
    version_page = reader.pages[-1].extract_text()
    pdf_commit = re.search(r"对应提交[：:]\s*([0-9a-f]{7,40})", version_page)
    if not pdf_commit or not commit.startswith(pdf_commit[1]):
        raise ValueError("PDF version stamp does not match the upstream source commit")
    section_pages, entry_pages, document_pages = pdf_locations(reader)
    if {e["id"] for e in entries} != set(entry_pages):
        raise ValueError("PDF bookmarks and source entries differ; use matching versions")
    for section in sections:
        location = section_pages[section["n"]]
        if comparable_title(section["title"]) != comparable_title(location["title"]):
            raise ValueError(f"PDF section title mismatch: {section['n']}")
        section["pdf_page"] = location["page"]
    for entry in entries:
        location = entry_pages[entry["id"]]
        if comparable_title(entry["title"]) != comparable_title(location["title"]):
            raise ValueError(f"PDF entry title mismatch: {entry['id']}")
        entry["pdf_page"] = location["page"]
    documents = []
    for path in sorted(set(re.findall(r"\]\((docs/[^)#/]+\.md)\)", readme))):
        markdown = (source_dir / path).read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", markdown, re.M)[1].strip()
        location = document_pages.get(comparable_title(title))
        if not location:
            raise ValueError(f"Long-form article missing from PDF: {path}")
        documents.append({"path": path, "title": title, "markdown": markdown,
                          "pdf_page": location["page"], "source_url": source_link(commit, path)})
    numbered = re.search(r"(\d+)\s*/\s*(\d+)\s*$", version_page)
    if not numbered or int(numbered[1]) != int(numbered[2]):
        raise ValueError("Cannot verify printed PDF page numbering")
    skill = source_dir / "skills/life-decision-guide/SKILL.md"
    return {
        "metadata": {"title": "高性价比人生指南", "author": "eternity4719",
                     "source_url": UPSTREAM, "source_commit": commit,
                     "pdf_source_commit": pdf_commit[1],
                     "snapshot_at": snapshot_at, "pdf_pages": len(reader.pages),
                     "printed_pages": int(numbered[2]), "page_offset": len(reader.pages)-int(numbered[2]),
                     "pdf_sha256": sha256(pdf), "skill_sha256": sha256(skill),
                     "skill_url": source_link(commit, "skills/life-decision-guide/SKILL.md"),
                     "pdf_url": f"{UPSTREAM}/releases/download/epub-latest/HowToLiveBetter.pdf",
                     "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                     "section_count": len(sections), "entry_count": len(entries),
                     "documents_count": len(documents), "schema_version": 1,
                     "upstream_files": {path: sha256(source_dir / path) for path in files},
                     "changes": "按章节和条目建立检索索引，保留原文；新增关键词/条件/问题检索及 PDF 跳转。性价比沿用作者算法。"},
        "sections": sections, "entries": entries, "documents": documents,
    }


def write_snapshot(snapshot: dict, source_dir: Path, pdf: Path, output_dir: Path) -> None:
    """Prepare every input before writing; repeating with the delivered PDF is safe."""
    payloads = {"guide.json": (json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))+"\n").encode("utf-8")}
    for source, name in ((pdf, "guide.pdf"),
                         (source_dir / "skills/life-decision-guide/SKILL.md", "skill.md"),
                         (source_dir / "LICENSE", "LICENSE-CONTENT.txt"),
                         (source_dir / "LICENSE-CODE", "LICENSE-UPSTREAM-CODE.txt")):
        payloads[name] = source.read_bytes()
    output_dir.mkdir(parents=True, exist_ok=True)
    pending = []
    try:
        for name, content in payloads.items():
            target = output_dir / name
            if target.is_file() and target.read_bytes() == content:
                continue
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix=f".{name}.", suffix=".tmp", delete=False) as temporary:
                pending.append((Path(temporary.name), target))
                temporary.write(content)
        # Each replacement is atomic. No original input is changed if a source
        # read or staging write fails; tests validate the complete set of hashes.
        for temporary, target in pending:
            os.replace(temporary, target)
    finally:
        for temporary, _ in pending:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--snapshot-at", required=True, help="Beijing snapshot time, YYYY-MM-DD HH:MM")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(args.source_dir, args.pdf, args.commit, args.snapshot_at)
    write_snapshot(snapshot, args.source_dir, args.pdf, args.output_dir)
    print(json.dumps({key: snapshot["metadata"][key] for key in
                      ("source_commit", "section_count", "entry_count", "documents_count", "pdf_pages", "printed_pages", "pdf_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
