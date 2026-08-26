"""Schema-v1 concept fables catalog: load, validate, upsert, filter."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIRED_ITEM_FIELDS = (
    "id",
    "concept",
    "field",
    "school",
    "definition",
    "story",
    "mappings",
    "questions",
    "tags",
    "created_at",
    "updated_at",
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLUG_WORD_RE = re.compile(r"[a-z0-9]+")
WHITESPACE_RE = re.compile(r"\s+")

_REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = _REPO_ROOT / "data" / "concept_fables.json"


def normalize_concept(value: Any) -> str:
    """Strip, NFKC, casefold, and collapse whitespace."""
    if value is None:
        text = ""
    else:
        text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    text = text.strip()
    text = WHITESPACE_RE.sub(" ", text)
    return text


def _normalize_display_text(value: Any) -> str:
    """NFKC + strip + collapse whitespace, preserving case for display fields."""
    if value is None:
        text = ""
    else:
        text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    text = WHITESPACE_RE.sub(" ", text)
    return text


def _empty_catalog() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "items": []}


def make_slug(concept: str, used_ids: set[str] | list[str] | None = None) -> str:
    """Build a lowercase ASCII-stable slug; hash fallback for non-ASCII concepts."""
    used = set(used_ids or [])
    normalized = normalize_concept(concept)
    ascii_text = (
        unicodedata.normalize("NFKD", normalized)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    words = SLUG_WORD_RE.findall(ascii_text.lower())
    if words:
        base = "-".join(words)
    else:
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
        base = f"concept-{digest}"

    candidate = base
    if candidate not in used:
        return candidate

    n = 2
    while True:
        candidate = f"{base}-{n}"
        if candidate not in used:
            return candidate
        n += 1


def _validate_iso_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not ISO_DATE_RE.match(value):
        raise ValueError(f"{field_name} must be an ISO date YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date YYYY-MM-DD") from exc
    return value


def _normalize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        raise ValueError("tags must be a list of non-empty strings")
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError("tags must be a list of non-empty strings")
        display = _normalize_display_text(tag)
        if not display:
            raise ValueError("tags must be a list of non-empty strings")
        key = normalize_concept(display)
        if key in seen:
            continue
        seen.add(key)
        result.append(display)
    return result


def validate_item(item: Any) -> dict[str, Any]:
    """Validate one catalog item; raise ValueError with a clear message."""
    if not isinstance(item, dict):
        raise ValueError("item must be an object")

    missing = [name for name in REQUIRED_ITEM_FIELDS if name not in item]
    if missing:
        raise ValueError(f"item missing required fields: {', '.join(missing)}")

    for name in ("id", "concept", "field", "definition", "story"):
        value = item[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    school = item["school"]
    if not isinstance(school, str):
        raise ValueError("school must be a string")

    story = item["story"]
    if len(story) > 1000:
        raise ValueError("story must be at most 1000 characters")

    mappings = item["mappings"]
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("mappings must be a non-empty list")
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("each mapping must be an object")
        if set(mapping.keys()) != {"story_element", "concept_element"}:
            raise ValueError(
                "each mapping must contain exactly story_element and concept_element"
            )
        for key in ("story_element", "concept_element"):
            value = mapping[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"mapping.{key} must be a non-empty string")

    questions = item["questions"]
    if not isinstance(questions, dict):
        raise ValueError("questions must be an object")
    if set(questions.keys()) != {"core", "transfer"}:
        raise ValueError("questions must contain exactly core and transfer")
    for key in ("core", "transfer"):
        value = questions[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"questions.{key} must be a non-empty string")

    tags = _normalize_tags(item["tags"])
    # Re-check after normalize path for validate-only: ensure original was valid list
    if not isinstance(item["tags"], list):
        raise ValueError("tags must be a list of non-empty strings")

    _validate_iso_date(item["created_at"], "created_at")
    _validate_iso_date(item["updated_at"], "updated_at")

    # Return a shallow-normalized copy for callers that want validated shape
    validated = {
        "id": item["id"].strip(),
        "concept": item["concept"].strip(),
        "field": item["field"].strip(),
        "school": school.strip() if isinstance(school, str) else school,
        "definition": item["definition"].strip(),
        "story": story,
        "mappings": [
            {
                "story_element": m["story_element"].strip(),
                "concept_element": m["concept_element"].strip(),
            }
            for m in mappings
        ],
        "questions": {
            "core": questions["core"].strip(),
            "transfer": questions["transfer"].strip(),
        },
        "tags": tags,
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }
    return validated


def validate_catalog(catalog: Any) -> dict[str, Any]:
    """Validate a full catalog document."""
    if not isinstance(catalog, dict):
        raise ValueError("catalog must be an object")
    if "schema_version" not in catalog:
        raise ValueError("catalog missing schema_version")
    if catalog["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be exactly {SCHEMA_VERSION}")
    if "items" not in catalog:
        raise ValueError("catalog missing items")
    items = catalog["items"]
    if not isinstance(items, list):
        raise ValueError("items must be a list")

    seen_ids: set[str] = set()
    seen_concepts: set[str] = set()
    validated_items: list[dict[str, Any]] = []
    for item in items:
        validated = validate_item(item)
        item_id = validated["id"]
        if item_id in seen_ids:
            raise ValueError(f"duplicate id: {item_id}")
        norm = normalize_concept(validated["concept"])
        if not norm:
            raise ValueError("concept must be a non-empty string")
        if norm in seen_concepts:
            raise ValueError(f"duplicate concept: {validated['concept']}")
        seen_ids.add(item_id)
        seen_concepts.add(norm)
        validated_items.append(validated)

    return {"schema_version": SCHEMA_VERSION, "items": validated_items}


def load_catalog(path: Path | str = CATALOG_PATH) -> dict[str, Any]:
    """Load and validate UTF-8 JSON catalog. Missing file → empty schema-v1."""
    catalog_path = Path(path)
    if not catalog_path.exists():
        return _empty_catalog()
    with catalog_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_catalog(data)


def save_catalog(catalog: dict[str, Any], path: Path | str = CATALOG_PATH) -> None:
    """Validate then write deterministic UTF-8 JSON via atomic same-dir replace."""
    validated = validate_catalog(catalog)
    catalog_path = Path(path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    tmp_path = catalog_path.with_name(f".{catalog_path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
        tmp_path.replace(catalog_path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def upsert_concept(
    catalog: dict[str, Any],
    payload: dict[str, Any],
    today: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Insert or update by normalized concept. Does not mutate inputs."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    working = validate_catalog(deepcopy(catalog))
    day = today or date.today().isoformat()
    _validate_iso_date(day, "today")

    concept = _normalize_display_text(payload.get("concept", ""))
    if not normalize_concept(concept):
        raise ValueError("concept must be a non-empty string")

    field = _normalize_display_text(payload.get("field", ""))
    if not field:
        raise ValueError("field must be a non-empty string")

    school_raw = payload.get("school", "")
    if not isinstance(school_raw, str):
        raise ValueError("school must be a string")
    school = _normalize_display_text(school_raw)

    definition = _normalize_display_text(payload.get("definition", ""))
    if not definition:
        raise ValueError("definition must be a non-empty string")

    story_raw = payload.get("story", "")
    if not isinstance(story_raw, str):
        raise ValueError("story must be a non-empty string")
    story = story_raw  # preserve internal whitespace; only check non-empty/length via validate
    if not story.strip():
        raise ValueError("story must be a non-empty string")
    if len(story) > 1000:
        raise ValueError("story must be at most 1000 characters")

    mappings_in = payload.get("mappings")
    if not isinstance(mappings_in, list) or not mappings_in:
        raise ValueError("mappings must be a non-empty list")
    mappings: list[dict[str, str]] = []
    for mapping in mappings_in:
        if not isinstance(mapping, dict):
            raise ValueError("each mapping must be an object")
        se = _normalize_display_text(mapping.get("story_element", ""))
        ce = _normalize_display_text(mapping.get("concept_element", ""))
        if not se or not ce:
            raise ValueError("mapping fields must be non-empty strings")
        mappings.append({"story_element": se, "concept_element": ce})

    questions_in = payload.get("questions")
    if not isinstance(questions_in, dict):
        raise ValueError("questions must be an object")
    core = _normalize_display_text(questions_in.get("core", ""))
    transfer = _normalize_display_text(questions_in.get("transfer", ""))
    if not core or not transfer:
        raise ValueError("questions.core and questions.transfer must be non-empty")
    questions = {"core": core, "transfer": transfer}

    tags = _normalize_tags(payload.get("tags", []))

    norm_concept = normalize_concept(concept)
    existing_index = None
    for index, item in enumerate(working["items"]):
        if normalize_concept(item["concept"]) == norm_concept:
            existing_index = index
            break

    if existing_index is None:
        used_ids = {item["id"] for item in working["items"]}
        item_id = make_slug(concept, used_ids)
        new_item = {
            "id": item_id,
            "concept": concept,
            "field": field,
            "school": school,
            "definition": definition,
            "story": story,
            "mappings": mappings,
            "questions": questions,
            "tags": tags,
            "created_at": day,
            "updated_at": day,
        }
        validate_item(new_item)
        working["items"].append(new_item)
        action = "created"
    else:
        previous = working["items"][existing_index]
        updated_item = {
            "id": previous["id"],
            "concept": concept,
            "field": field,
            "school": school,
            "definition": definition,
            "story": story,
            "mappings": mappings,
            "questions": questions,
            "tags": tags,
            "created_at": previous["created_at"],
            "updated_at": day,
        }
        validate_item(updated_item)
        working["items"][existing_index] = updated_item
        action = "updated"

    validated = validate_catalog(working)
    return validated, action


def filter_items(
    items: list[dict[str, Any]],
    query: str = "",
    field: str = "全部",
    sort: str = "最新",
) -> list[dict[str, Any]]:
    """Filter and sort items without mutating the input list or items."""
    results = [deepcopy(item) for item in items]

    field_norm = normalize_concept(field) if field else ""
    if field_norm and field_norm not in {"全部", ""}:
        results = [
            item
            for item in results
            if normalize_concept(item.get("field", "")) == field_norm
        ]

    query_norm = normalize_concept(query) if query else ""
    if query_norm:
        filtered: list[dict[str, Any]] = []
        for item in results:
            haystacks = [
                normalize_concept(item.get("concept", "")),
                normalize_concept(item.get("field", "")),
                normalize_concept(item.get("school", "")),
                normalize_concept(item.get("definition", "")),
            ]
            tags = item.get("tags") or []
            if isinstance(tags, list):
                haystacks.extend(normalize_concept(tag) for tag in tags)
            if any(query_norm in text for text in haystacks):
                filtered.append(item)
        results = filtered

    if sort == "名称":
        results.sort(key=lambda item: normalize_concept(item.get("concept", "")))
    else:
        # 最新: updated_at desc, then concept desc
        results.sort(
            key=lambda item: (
                item.get("updated_at", ""),
                normalize_concept(item.get("concept", "")),
            ),
            reverse=True,
        )

    return results


def select_item(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    """Return a copy of the item with matching id, or None."""
    for item in items:
        if item.get("id") == item_id:
            return deepcopy(item)
    return None
