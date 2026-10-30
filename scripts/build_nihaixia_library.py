"""Build a subject knowledge base from local authored study, never raw corpus.

Build is offline. Publishing is an explicit separate command and uses the
toolbox's existing private-data connection. The manifest is switched last.
"""

import argparse
from collections import Counter
from datetime import date
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import github_backup_sync as sync
from utils import nihaixia_knowledge as kb


# These fields describe reading work and software receipts, not the theory.
# All other fields are retained; new unknown fields therefore cannot disappear.
PROCESS_FIELDS = set("""
schema_version note_id created_on authored_on authored_by reviewed_chunks reviewed_transcripts
reviewed_images reviewed_pdf_pages reviewed_video_frames reviewed_video_frames_count
encoding_review reading_progress book_coverage line_by_line_study frame_reviews pdf_page_reviews
prior_note_reuse supplementary_reading review_status coordinator_review coverage_meaning coverage
source_reviews visual_reviews reading_scope time_accounting reviewed_existing_notes
focused_chunk_rereads_do_not_count_as_new_learning new_original_media_minutes
coordinator_candidate_revision review_metadata_update whole_source_coverage visual_review_receipt
coverage_receipt source_metadata_receipt prior_reused_notes baselines learning_method
visual_review native_doc_review calculation_review review_refinement baseline review_level
source_reading source27_reuse next_batch revision_history textbook_page_reviews
verification implementation_status coverage_matrix coverage_totals implementation_changes
implementation prior_accepted_comparison validation_boundary prior_note_comparison
case_timeline_checks reading_range supplemental_original_read reviewed_document_regions
authorship_and_reading_limits prior_reuse original_document_review independent_review
review_history coordinator_review_targets reused_source117 native_supplement_reviews
study_method verification_meaning rules title topic domain sources source_ids
""".split())

IGNORED_DIRS = {"accepted", "baseline", "drafts", "backup", "backup_before_rule_correction"}
PROCESS_FILES = re.compile(
    r"^(?:研习目录|持续研习计划|每轮量化标准|学习方法与执行记录|读前理解基线|本轮分工|"
    r"source_coverage_audit|coverage_gap_analysis|迁移题首答)")
PROCESS_HEADINGS = re.compile(
    r"^(?:[一二三四五六七八九十\d]+[、. ]+)?(?:"
    r"(?:本轮|本次)?(?:实际)?学习量(?:与验收|与成果)?|量化统计|"
    r"(?:本轮|本次)(?:文件|分工|完成情况)|(?:验收|验证|执行|投入|复研)记录|"
    r"验收结果|文件清单|后续任务|后续计划|计时|净学习时间|墙钟时间|"
    r"验证|实施说明|实施变更|执行量记录|原始资料保护)$")
PROCESS_LINES = re.compile(
    r"^(?:研读者[：:]|(?:本轮|本次)已?完成\d+个有效课程|材料(?:总长|合计)|"
    r"(?:正式笔记|笔记仍为|规则仍为|stale\s*[=:：])|"
    r"(?:读取|阅读|抽帧|验收|计时|执行)(?:时间|范围|统计|记录)[：:]|"
    r"原片.*(?:哈希|SHA-256).*一致|\d+\.\d+分钟是|"
    r"字数按文件|逐源路径、块号|本轮从建清单|本轮新增唯一课程覆盖)")
COMPARISON_FILES = re.compile(r"^(?:cross_course|conditional|condition)_comparisons\.json$")
BACKUP_DIR = re.compile(r"backup|baseline|draft|frames|snapshots|material|read_cache", re.I)
TECH_KEYS = {"round_id", "round", "reviewer", "reviewed_at", "created_at", "schema_version",
             "count", "cross_course_count", "total", "cross_course", "counting", "counting_scope",
             "state_changed", "candidate_sha256", "status", "pack_id", "group", "grader"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def clean_title(title):
    title = re.sub(r"^#+\s*", "", str(title)).strip()
    title = re.sub(r"第\s*\d+\s*轮(?:扩大)?(?:研习札记|研习总论|研习报告|研习|复习|深化复研)?[：:｜|·\s]*", "", title)
    title = re.sub(r"\bR\d+\s*", "", title, flags=re.I)
    title = re.sub(r"(?:第[一二三四五六七八九十\d]+批|连续研习|全文研读|全篇研习)", "", title)
    title = re.sub(r"(?:本轮深化研习报告|本轮研习报告|分组研习报告|研习报告)", "", title)
    title = re.sub(r"\bpack[_ ]*[a-d]\s*[：:]?\s*", "", title, flags=re.I)
    title = re.sub(r"(?:20\d{2}[_-]\d{2}[_-]\d{2})", "", title)
    title = re.sub(r"[（(][）)]", "", title).strip(" _—：:｜|·-")
    return title or "理论与应用"


def clean_markdown(text):
    """Remove work accounting sections; preserve every paragraph of theory."""
    kept, omitted, skip_level, in_code = [], [], None, False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        heading = None if in_code else re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            if skip_level and level <= skip_level:
                skip_level = None
            if skip_level:
                continue
            if level == 1:
                continue
            if PROCESS_HEADINGS.search(title):
                omitted.append(title)
                skip_level = level
                continue
        if skip_level:
            continue
        if PROCESS_LINES.search(line.strip()):
            omitted.append(line.strip()[:120])
            continue
        kept.append(line)
    body = re.sub(r"\n{4,}", "\n\n\n", "\n".join(kept)).strip()
    return body, omitted


def conceptual_title(title, body):
    """Give old reports a theory title; their substantive text stays intact."""
    if (title == "理论与应用" or not re.search(r"[\u4e00-\u9fff]", title)
            or re.search(r"独立复核|研习报告|续接|跨课比较独立|逐项复核|量化达标", title)):
        candidates = re.findall(r"\*\*([^*\n]{6,100})\*\*", body)
        candidates += re.findall(r"^#{2,4}\s+(.{6,100})$", body, re.M)
        for candidate in candidates:
            if not re.search(r"来源|范围|本轮|本次|完成|统计|验收|复核|接受|分钟|文件|执行|覆盖|摘要|结论|研读|阅读", candidate):
                return clean_title(candidate)
        # A complete sentence is a navigation label, not a substitute for text.
        for paragraph in body.split("\n\n"):
            if (len(paragraph) > 25 and re.search(r"[\u4e00-\u9fff]", paragraph)
                    and not re.search(r"^#|^\||^[*-]|^>|\.(?:json|md)|本轮|本次|分钟|统计|执行|source\d|sha256", paragraph)):
                return clean_title(paragraph.split("。")[0][:100])
    return title


def embedded_observations(note):
    """Keep conceptual observations embedded inside otherwise technical receipts."""
    observations = []
    semantic_key = re.compile(r"understand|interpret|observ|meaning|finding|correct|conclu|decision|rule|comparison|exception|unresolved|limitation|理论|结论|判断|理解|修正|条件|例外", re.I)

    def visit(value, trail, semantic=False):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, trail + [key], semantic or bool(semantic_key.search(key)))
        elif isinstance(value, list):
            for child in value:
                visit(child, trail, semantic)
        elif isinstance(value, str) and semantic and len(value) >= 12 and re.search(r"[\u4e00-\u9fff]", value):
            observations.append({"说明类别": "/".join(trail), "理解与校正": value})
    for key in PROCESS_FIELDS - {"rules", "reviewed_chunks", "reviewed_transcripts", "sources", "source_ids"}:
        if key in note:
            visit(note[key], [key])
    return observations


def display_value(value, depth=0):
    if value is None:
        return "未注明"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "未另列"
        return "\n\n".join(("- " if not isinstance(item, (dict, list)) else "") +
                           display_value(item, depth + 1) for item in value)
    if isinstance(value, dict):
        lines = []
        for key, val in value.items():
            if key in {"id", "chunk_hash", "sha256", "hash", "source_hash", "note_sha256"}:
                continue
            label = kb.FIELD_LABELS.get(key, key)
            lines.append(f"**{label}**\n\n{display_value(val, depth + 1)}")
        return "\n\n".join(lines)
    raise TypeError(type(value))


def domain_for(title, text="", hint=""):
    probe = f"{hint} {title}".casefold()
    if re.search(r"baibao|bed_|hanlong|luopan|luojing|compass|sanhe|liushen|short_supp|白宝全|侯氏|罗经|罗盘|撼龙|三合|六神用法", probe):
        return "supplements"
    if re.search(r"earth|dimaidao|kanyu|地脉|阳宅|堪舆|房位|床位|开门放水", probe):
        return "earth"
    if re.search(r"总纲|体系的主干|综合合参方法|体系导航", probe):
        return "framework"
    if re.search(r"minggua|四柱命卦|先后天|先天.*后天|命卦", probe):
        return "minggua"
    if re.search(r"ziwei|紫微|命身|财禄|六亲|职业|财源|鸾喜|婚期|夫妻|才性.*任用", probe):
        if re.search(r"大限|小限|限年|流年|时间轴|交运|时序", probe):
            return "timing"
        return "ziwei"
    if re.search(r"renjiandao|yijing|人间道|易经|六爻|卦|时位|进退|任贤|守成|济难|成事", probe):
        return "yijing"
    if re.search(r"命例|男命|女命|婚|大限|小限", probe):
        return "cases"
    if text:
        weights = {"ziwei": ("命宫", "财帛", "官禄", "夫妻宫"),
                   "timing": ("大限", "小限", "流年"), "minggua": ("元堂", "先天卦", "后天卦"),
                   "yijing": ("九二", "六二", "卦", "人间道"), "earth": ("阳宅", "地脉", "房位")}
        scores = {key: sum(text.count(word) for word in words) for key, words in weights.items()}
        winner = max(scores, key=scores.get)
        if scores[winner]:
            return winner
    return "framework"


def source_catalog(connection):
    return {row["id"]: dict(row) for row in connection.execute(
        "SELECT id,relative_path,authority,content_hash FROM sources")}


def evidence_refs(value, connection, sources):
    result = []

    def visit(obj):
        if isinstance(obj, list):
            for child in obj:
                visit(child)
        elif isinstance(obj, dict):
            sid = obj.get("source_id")
            if isinstance(sid, int) and sid in sources:
                locator = obj.get("page_or_time", "")
                cid, tid = obj.get("chunk_id"), obj.get("transcript_id")
                if not locator and isinstance(cid, int):
                    row = connection.execute("SELECT page_or_time FROM chunks WHERE id=? AND source_id=?", (cid, sid)).fetchone()
                    locator = row[0] if row else ""
                if not locator and isinstance(tid, int):
                    row = connection.execute("SELECT page_or_time FROM oral_chunks WHERE id=? AND source_id=?", (tid, sid)).fetchone()
                    locator = row[0] if row else ""
                result.append(f"{sources[sid]['relative_path']} · {locator or '见笔记所引图页'} · {sources[sid]['authority']}")
            for val in obj.values():
                if isinstance(val, (dict, list)):
                    visit(val)
    visit(value)
    return list(dict.fromkeys(result))


def note_title(path, note):
    title = note.get("title") or note.get("topic")
    md = path.with_suffix(".md")
    if not title and md.exists():
        title = next((line for line in md.read_text(encoding="utf-8-sig").splitlines() if line.startswith("# ")), None)
    return clean_title(title or path.stem)


def build(source_root, output, publication_date):
    learning = source_root / "data" / "learning"
    if not learning.is_dir() or not (source_root / "src" / "nihaixia_kb").is_dir():
        raise ValueError("请指定本地知识库项目，不要指定原始视频和书籍目录。")
    if not output.is_relative_to(source_root / "data"):
        raise ValueError("本机构建成果须留在知识库项目 data 目录。")
    os.environ["NIHAIXIA_PROJECT_ROOT"] = str(source_root)
    sys.path.insert(0, str(source_root / "src"))
    from nihaixia_kb.learning import read_accepted_notes
    accepted = read_accepted_notes()
    if accepted["stale_notes"]:
        raise ValueError("存在失效的正式笔记；先复核，再发布。")
    connection = sqlite3.connect((source_root / "data" / "kb.sqlite").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    sources = source_catalog(connection)
    entries, input_inventory, omissions, rule_hashes = [], [], [], {}
    accepted_paths = set()
    all_source_ids = set()

    def add(entry):
        entry.setdefault("tags", [])
        entry.setdefault("sources", [])
        entry.setdefault("order", 99)
        entries.append(entry)

    for accepted_note in accepted["notes"]:
        note = accepted_note["note"]
        path = Path(accepted_note["path"])
        accepted_paths.add(path.with_suffix(".md").resolve())
        title = note_title(path, note)
        hint = note.get("domain", "") + " " + note["note_id"]
        relative = path.relative_to(learning).as_posix()
        input_inventory.append({"path": relative, "sha256": accepted_note["sha256"], "type": "accepted_note"})
        for rule in note["rules"]:
            rid = f"rule:{note['note_id']}:{rule['id']}"
            rule_hashes[rid] = kb.digest(kb.canonical_json(rule))
            rt = rule.get("title") or rule["statement"].split("。")[0]
            body = "\n\n".join(f"### {kb.FIELD_LABELS.get(key, key)}\n\n{display_value(value)}"
                                for key, value in rule.items() if key not in {"id", "title", "domain", "evidence"})
            refs = evidence_refs(rule, connection, sources)
            if not refs:
                refs = evidence_refs(note.get("reviewed_chunks", []), connection, sources)
            add({"id": rid, "kind": "规则", "domain": domain_for(rt, body, hint),
                 "title": clean_title(rt), "body": body, "rule": rule,
                 "sources": refs, "tags": [title, "已接受的研习规则"],
                 "provenance": [{"file": relative, "sha256": accepted_note["sha256"], "rule_id": rule["id"]}]})
        details = {key: value for key, value in note.items() if key not in PROCESS_FIELDS}
        observations = embedded_observations(note)
        if observations:
            details["图文观察与校正说明"] = observations
        # Note-level matrices, derivations, corrections and caveats are retained
        # independently of rules; a short rule cannot stand in for this material.
        if details:
            add({"id": f"note:{note['note_id']}", "kind": "专题", "domain": domain_for(title, hint=hint),
                 "title": title + "：扩展说明与完整条件", "body": display_value(details), "details": details,
                 "sources": evidence_refs(note.get("reviewed_chunks", []), connection, sources),
                 "provenance": [{"file": relative, "sha256": accepted_note["sha256"]}]})
        for row in note.get("reviewed_chunks", []):
            if isinstance(row, dict) and isinstance(row.get("source_id"), int):
                all_source_ids.add(row["source_id"])

    # Full authored chapters are kept alongside the structured rules. Book/video
    # snapshots, receipts, superseded backups and initial uncorrected answers stay local.
    chapter_paths = list(learning.rglob("*.md"))
    editorial = source_root / "data" / "publication" / "editorial"
    if editorial.exists():
        chapter_paths.extend(editorial.glob("*.md"))
    for path in sorted(chapter_paths):
        rel = path.relative_to(source_root / "data").as_posix()
        parts = path.relative_to(source_root / "data").parts
        if any(part in IGNORED_DIRS or "backup" in part.lower() for part in parts) or "可删" in path.name:
            continue
        if "notes" in parts and path.resolve() not in accepted_paths:
            omissions.append({"file": rel, "reason": "不属于当前有效笔记"})
            continue
        if PROCESS_FILES.search(path.name):
            omissions.append({"file": rel, "reason": "工作计划、目录、初答或执行统计"})
            continue
        raw = path.read_text(encoding="utf-8-sig")
        title = clean_title(next((line for line in raw.splitlines() if line.startswith("# ")), path.stem))
        body, removed = clean_markdown(raw)
        title = conceptual_title(title, body)
        if removed:
            omissions.append({"file": rel, "process_sections": removed})
        if len(body.strip()) < 80:
            omissions.append({"file": rel, "reason": "去除执行统计后无独立理论正文"})
            continue
        kind = "疑点与取舍" if re.search(r"冲突|疑点|反馈|取舍矩阵", title) else "专题"
        if "总纲" in title or "体系" in title or "总论" in title:
            kind = "总纲"
        domain = domain_for(title, body, rel)
        if "editorial" in parts:
            kind, domain = "总纲", "framework"
        source_hash = kb.digest(path.read_bytes())
        input_inventory.append({"path": rel, "sha256": source_hash, "type": "chapter"})
        add({"id": "chapter:" + kb.digest(rel)[:24], "kind": kind, "domain": domain,
             "title": title, "body": body, "tags": ["研习者综合解释"],
             "order": 0 if "editorial" in parts else (10 if kind == "总纲" else 50),
             "provenance": [{"file": rel, "sha256": source_hash}],
             "sources": ["来源定位保留在正文；课程命例与自拟例按原文分别注明。"]})

    for path in sorted(learning.rglob("*.json")):
        if not COMPARISON_FILES.fullmatch(path.name) or any(BACKUP_DIR.search(p) for p in path.relative_to(learning).parts[:-1]):
            continue
        document = read_json(path)
        comparisons = document if isinstance(document, list) else document.get("comparisons", document.get("items", []))
        if not isinstance(comparisons, list):
            continue
        rel = path.relative_to(learning).as_posix()
        source_hash = kb.digest(path.read_bytes())
        input_inventory.append({"path": rel, "sha256": source_hash, "type": "comparisons"})
        for index, item in enumerate(comparisons):
            if not isinstance(item, dict):
                continue
            content = {key: value for key, value in item.items() if key not in TECH_KEYS}
            title = (item.get("question") or item.get("title") or item.get("topic")
                     or item.get("comparison") or item.get("conclusion") or f"条件对照 {index + 1}")
            if not isinstance(title, str):
                title = f"条件对照 {index + 1}"
            body = display_value(content)
            add({"id": "comparison:" + kb.digest(rel + ":" + str(index))[:24], "kind": "条件对照",
                 "domain": domain_for(title, body), "title": clean_title(title), "body": body,
                 "details": content, "sources": evidence_refs(item, connection, sources),
                 "provenance": [{"file": rel, "sha256": source_hash, "index": index}]})
    connection.close()

    # Exact duplicate chapters/comparisons merge only their provenance. No
    # summarization or fuzzy merging is allowed to alter distinct conditions.
    seen, unique = {}, []
    for entry in entries:
        key = (entry["kind"], kb.digest(entry["body"]))
        if entry["kind"] != "规则" and key in seen:
            prior = seen[key]
            prior["provenance"].extend(entry["provenance"])
            prior["sources"] = list(dict.fromkeys(prior["sources"] + entry["sources"]))
        else:
            seen[key] = entry
            unique.append(entry)
    entries = sorted(unique, key=lambda e: e["id"])
    revision = kb.digest(kb.canonical_json(entries))
    revision_root = output / "data" / "nihaixia" / "releases" / revision
    parts, pending = [], []

    def flush():
        if not pending:
            return
        payload = kb.pack_part(pending)
        if len(payload.encode()) > kb.MAX_PART_BYTES:
            raise ValueError("单条知识内容超出分卷容量。")
        path = revision_root / f"part-{len(parts):03d}.json"
        write_text(path, payload)
        parts.append({"path": path.relative_to(output).as_posix(), "sha256": kb.digest(payload),
                      "entries": len(pending), "bytes": len(payload.encode())})
        pending.clear()

    # Batch by uncompressed size; each part is below GitHub Contents API's
    # base64 limit. A final compressed bound is also checked by flush().
    size = 0
    for entry in entries:
        amount = len(kb.canonical_json(entry).encode())
        if pending and size + amount > 1_350_000:
            flush()
            size = 0
        pending.append(entry)
        size += amount
    flush()
    counts = {"entries": len(entries), "rules": len(rule_hashes), "accepted_notes": len(accepted["notes"]),
              "chapters": sum(e["kind"] in {"专题", "总纲", "疑点与取舍"} for e in entries),
              "comparisons": sum(e["kind"] == "条件对照" for e in entries),
              "characters": sum(len(e["body"]) for e in entries), "source_documents": len(input_inventory)}
    manifest = {"schema_version": kb.SCHEMA_VERSION, "title": "倪海厦玄学知识库", "revision": revision,
                "updated_on": publication_date, "update_mode": "manual_only", "parts": parts, "counts": counts,
                "domains": dict(Counter(e["domain"] for e in entries)),
                "boundary": "保存当前已接受规则和截至本版的研习理解；未决规则、不同作者及教学命例分别保留。"}
    kb.validate_manifest(manifest)
    kb.validate_entries(entries, manifest)
    published_rules = {e["id"]: kb.digest(kb.canonical_json(e["rule"])) for e in entries if e["kind"] == "规则"}
    if published_rules != rule_hashes:
        raise ValueError("正式规则逐条对账失败。")
    write_text(output / kb.MANIFEST_PATH, kb.canonical_json(manifest))
    write_text(output / "library.json", kb.canonical_json({"manifest": manifest, "entries": entries}))
    write_text(output / "source_inventory.json", json.dumps(input_inventory, ensure_ascii=False, indent=2))
    write_text(output / "coverage_audit.json", json.dumps({"counts": counts, "all_rules_exact": True,
               "stale_notes": [], "rule_hashes": rule_hashes, "process_omissions": omissions,
               "no_raw_media_uploaded": True, "revision": revision}, ensure_ascii=False, indent=2))
    for domain, label in kb.DOMAINS.items():
        selected = [entry for entry in entries if entry["domain"] == domain]
        write_text(output / "chapters" / f"{label}.md", kb.export_markdown(selected, label))
    print(json.dumps({"result": "built", "revision": revision, "counts": counts, "parts": len(parts)}, ensure_ascii=False))


def local_secrets():
    import tomllib
    path = ROOT / ".streamlit" / "secrets.toml"
    return tomllib.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def publish(output):
    library = read_json(output / "library.json")
    manifest = kb.validate_manifest(library["manifest"])
    kb.validate_entries(library["entries"], manifest)
    secrets = local_secrets()
    transport = kb.private_connection(secrets=secrets)
    current = sync.read_file_from_github(kb.MANIFEST_PATH, secrets=secrets, session=transport)
    if not current.get("ok") and current.get("reason") != "missing_remote_file":
        raise ValueError("现有云端版本未确认，未发布。")
    expected_sha = current.get("sha") if current.get("ok") else None
    if current.get("ok"):
        old = kb.load_library(secrets=secrets, session=transport)
        if old["manifest"]["revision"] == manifest["revision"]:
            print(json.dumps({"result": "unchanged", "revision": manifest["revision"]}, ensure_ascii=False))
            return
        old_ids = {entry["id"] for entry in old["entries"]}
        new_ids = {entry["id"] for entry in library["entries"]}
        if old_ids - new_ids:
            raise ValueError("本次构建缺少已发布条目；须先合并或明确修正原因，不能自动删减。")
    for part in manifest["parts"]:
        path = output / part["path"]
        text = path.read_text(encoding="utf-8")
        kb.unpack_part(text, part["sha256"])
        remote = sync.read_file_from_github(part["path"], secrets=secrets, session=transport)
        if remote.get("ok"):
            if remote["content"] != text:
                raise ValueError("同版本分卷内容不同，未覆盖。")
        elif remote.get("reason") == "missing_remote_file":
            result = sync.sync_file_to_github(path, part["path"], "data: publish Ni Haixia knowledge volume",
                                            secrets=secrets, session=transport, expected_sha=None)
            if not result.get("ok"):
                raise ValueError("知识库分卷未上传。")
        else:
            raise ValueError("知识库分卷状态未确认。")
        verified = sync.read_file_from_github(part["path"], secrets=secrets, session=transport)
        if not verified.get("ok") or kb.digest(verified["content"]) != part["sha256"]:
            raise ValueError("知识库分卷回读不一致；现有目录保持不变。")
    # Atomic switch only after every immutable volume is uploaded and read back.
    result = sync.sync_file_to_github(output / kb.MANIFEST_PATH, kb.MANIFEST_PATH,
                                     "data: update manually curated Ni Haixia knowledge library",
                                     secrets=secrets, session=transport, expected_sha=expected_sha)
    if not result.get("ok"):
        raise ValueError("目录切换未完成。")
    verified = kb.load_library(secrets=secrets, session=transport)
    if verified["manifest"]["revision"] != manifest["revision"]:
        raise ValueError("云端目录已发生变化，请重新核对。")
    receipt = {"result": "published_and_verified", "revision": manifest["revision"],
               "manifest_sha": verified["manifest_sha"], "counts": manifest["counts"]}
    write_text(output / "publication_receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "publish"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    if args.action == "build":
        if not args.source_root:
            parser.error("build requires --source-root")
        build(args.source_root.resolve(), args.output.resolve(), args.date)
    else:
        publish(args.output.resolve())


if __name__ == "__main__":
    main()
