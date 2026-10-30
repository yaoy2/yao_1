"""M32 knowledge documents: private, versioned, read-only, and lossless."""

import base64
import gzip
import hashlib
import io
import json
import re

from utils import github_backup_sync as sync


PRIVATE_REPO = "yaoy2/yao_1-data"
BRANCH = "main"
MANIFEST_PATH = "data/nihaixia/manifest.json"
SCHEMA_VERSION = 1
MAX_PART_BYTES = 900_000
MAX_DECODED_BYTES = 16_000_000
MAX_PARTS = 32
DOMAINS = {
    "framework": "总纲与合参方法",
    "ziwei": "紫微命身与六亲",
    "timing": "大限小限与流年",
    "minggua": "四柱命卦",
    "yijing": "易经与人间道",
    "earth": "阳宅与地脉",
    "supplements": "各家补充支系",
    "cases": "命例与条件对照",
}
KINDS = ("总纲", "规则", "专题", "条件对照", "疑点与取舍")
FIELD_LABELS = {
    "statement": "判断", "conditions": "适用条件", "exceptions": "例外与限制",
    "derivation": "推导依据", "decision_steps": "判断顺序", "counterexamples": "反例",
    "authority": "作者与支系", "source_attribution": "来源归属", "authorship": "作者归属",
    "source_layer": "材料层次", "interpretation_status": "解释性质",
    "hexagram": "卦名", "upper_trigram": "上卦", "lower_trigram": "下卦",
    "resident_role": "居住者身份", "room_direction": "房位", "question": "问题",
    "answer": "判断与解释", "who": "主体", "situation": "处境", "duty": "职责",
    "action": "行动取舍", "boundary": "使用边界", "unresolved": "尚未解决",
    "limitations": "适用限制", "contrasts": "条件对照", "synthesis": "综合理解",
    "comparisons": "对照", "conditional_comparisons": "条件对照", "cases": "命例",
    "exercises": "应用推演", "source_boundaries": "来源边界", "scope_boundaries": "适用边界",
    "new_understanding_vs_prior": "深化理解", "prior_comparison": "与既有判断的对照",
    "prior_rule_ids": "关联规则", "derived_from_rule_ids": "推导所据规则",
    "supporting_note_rules": "相关笔记规则", "basis_rules": "基础规则",
    "supersedes": "修正的旧规则", "counter_evidence": "相反材料",
    "whole_hexagram_readings": "整卦理解", "six_line_matrices": "六爻条件表",
    "hexagram_studies": "卦义研习", "six_line_digests": "六爻解释",
    "method_contracts": "方法适用范围", "tables": "规则表", "algorithm_tables": "排法表",
    "manual_examples": "演算实例", "worked_checks": "推导核对", "derivation_checks": "推导检验",
    "course_comparisons": "课程对照", "course_digests": "课程理解", "course_studies": "专题理解",
    "textual_issues": "文本疑义", "discrepancies": "版本差异", "ambiguities": "歧义",
    "corrections": "修正", "corrections_to_prior_notes": "既有判断修正",
    "condition_comparisons": "条件对照", "condition_exercises": "条件变化推演",
    "historical_annual_examples": "流年实例", "original_cases": "原课命例",
    "source_layers": "来源层次", "interpretation_context": "推断语境",
    "hexagram_judgments": "分卦判断", "judgments_reading_notes": "判断说明",
    "water_flip_table": "水法翻卦表", "bagua_table": "八卦对应表",
    "bed_position_comparisons": "床位条件对照", "chapter_comparisons": "章节对照",
    "six_spirit_six_relation_matrix": "六神六亲对照", "trigram_basis": "卦象依据",
    "unresolved_interfaces": "尚缺的衔接规则", "unresolved_items": "未决问题",
    "difficulties_resolved": "已厘清的问题", "resolved": "已有解决依据",
    "source_equivalence": "来源对应", "scope_exclusions": "不适用范围",
    "source_path": "来源", "page_or_time": "页码或时点", "quote_exact": "直接摘录",
    "confidence": "抽取置信度", "evidence": "出处", "summary": "理解要点",
    "topic": "主题", "title": "标题", "name": "名称", "reason": "理由",
    "finding": "判断", "findings": "判断", "conclusion": "结论", "meaning": "含义",
    "changed_understanding": "理解变化", "application": "应用", "interpretation": "解释",
    "difference": "差异", "common": "共同点", "details": "详细说明",
    "rule": "规则", "rules": "规则", "sources": "来源", "source_id": "来源编号",
    "kind": "类别", "text": "内容", "note": "说明", "notes": "说明",
}


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def pack_part(entries):
    raw = canonical_json({"entries": entries}).encode("utf-8")
    return canonical_json({"encoding": "gzip+base64", "sha256": digest(raw),
                           "data": base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")})


def unpack_part(text, expected_hash):
    if len(text.encode("utf-8")) > MAX_PART_BYTES or digest(text) != expected_hash:
        raise ValueError("知识库分卷不完整。")
    part = json.loads(text)
    if part.get("encoding") != "gzip+base64":
        raise ValueError("知识库分卷格式不支持。")
    compressed = base64.b64decode(part["data"], validate=True)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_DECODED_BYTES + 1)
    if len(raw) > MAX_DECODED_BYTES or digest(raw) != part.get("sha256"):
        raise ValueError("知识库分卷校验未通过。")
    entries = json.loads(raw)["entries"]
    if not isinstance(entries, list):
        raise ValueError("知识库条目格式错误。")
    return entries


def validate_manifest(manifest):
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION
            or not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("revision", "")))):
        raise ValueError("知识库目录版本无效。")
    parts = manifest.get("parts", [])
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        raise ValueError("知识库分卷数量无效。")
    prefix = f"data/nihaixia/releases/{manifest['revision']}/"
    seen = set()
    for part in parts:
        path = part.get("path", "")
        if (not path.startswith(prefix) or not re.fullmatch(r"part-\d{3}\.json", path[len(prefix):])
                or path in seen or not re.fullmatch(r"[a-f0-9]{64}", part.get("sha256", ""))):
            raise ValueError("知识库分卷路径无效。")
        seen.add(path)
    return manifest


def validate_entries(entries, manifest):
    ids = set()
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
                or not entry["id"] or entry["id"] in ids or entry.get("domain") not in DOMAINS
                or entry.get("kind") not in KINDS or not isinstance(entry.get("body"), str)
                or not isinstance(entry.get("title"), str) or not entry["title"]):
            raise ValueError("知识库条目无效或重复。")
        ids.add(entry["id"])
    if len(entries) != manifest["counts"]["entries"]:
        raise ValueError("知识库条目数量不匹配。")
    if sum(e["kind"] == "规则" for e in entries) != manifest["counts"]["rules"]:
        raise ValueError("规则数量不匹配。")
    if digest(canonical_json(entries)) != manifest["revision"]:
        raise ValueError("知识库整体版本校验未通过。")
    return entries


def private_connection(secrets=None, environ=None, session=None):
    config = sync.get_backup_sync_config(secrets, environ)
    if not config["enabled"] or config["repo"].casefold() != PRIVATE_REPO or config["branch"] != BRANCH:
        raise ValueError("尚未连接指定的私有知识库。")
    transport = sync._session(config, session)
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {config['token']}",
               "X-GitHub-Api-Version": "2022-11-28"}
    response = transport.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}", headers=headers,
                             timeout=20, allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("暂时无法核对知识库访问权限。")
    metadata = response.json()
    if metadata.get("private") is not True or str(metadata.get("full_name", "")).casefold() != PRIVATE_REPO:
        raise ValueError("知识库仓库未确认为私有，已停止读取。")
    return transport


def load_library(secrets=None, environ=None, session=None):
    """Call only after the page's password gate. Never fall back to public content."""
    transport = private_connection(secrets, environ, session)

    def read(path):
        result = sync.read_file_from_github(path, secrets, environ, transport)
        if not result.get("ok"):
            raise ValueError("知识库文件暂时未读到。")
        return result

    current = read(MANIFEST_PATH)
    manifest = validate_manifest(json.loads(current["content"]))
    entries = []
    for part in manifest["parts"]:
        entries.extend(unpack_part(read(part["path"])["content"], part["sha256"]))
    validate_entries(entries, manifest)
    return {"manifest": manifest, "entries": entries, "manifest_sha": current["sha"]}


def search_entries(entries, query="", domain=None, kinds=None):
    terms = [term.casefold() for term in query.split() if term.strip()]
    found = []
    for entry in entries:
        if domain and entry["domain"] != domain or kinds and entry["kind"] not in kinds:
            continue
        title = entry["title"].casefold()
        text = (title + "\n" + entry["body"] + "\n" + " ".join(entry.get("tags", []))).casefold()
        if all(term in text for term in terms):
            score = sum(6 if term in title else 1 for term in terms)
            found.append((score, entry))
    return [entry for _, entry in sorted(found, key=lambda pair: (
        -pair[0], pair[1].get("order", 99), pair[1]["title"], pair[1]["id"]))]


def reader_markdown(text):
    """Keep text but neutralize local files, images and unresolvable source links."""
    text = re.sub(r"!\[([^\]]*)\]\([^\n]*\)", r"（图示：\1；原图保存在本机资料库）", text)
    text = re.sub(r"\[([^\]]+)\]\((?:<[^>]+>|[^)]+)\)", r"\1", text)
    return text


def export_markdown(entries, title="倪海厦玄学知识库"):
    sections = [f"# {title}", "按主题保存的知识正文；规则、条件、例外、推导及来源均保留。"]
    for entry in entries:
        sections.extend([f"\n## {entry['title']}",
                         f"{DOMAINS[entry['domain']]} · {entry['kind']}\n", reader_markdown(entry["body"])])
        refs = entry.get("sources", [])
        if refs:
            sections.append("\n出处：\n" + "\n".join(f"- {ref}" for ref in refs))
        for evidence in entry.get("rule", {}).get("evidence", []):
            quote = evidence.get("quote_exact") or evidence.get("excerpt")
            if quote:
                sections.append("原文短引：\n\n" + quote)
    return "\n\n".join(sections)
