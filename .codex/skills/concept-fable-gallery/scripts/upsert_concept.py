#!/usr/bin/env python3
"""Deterministic CLI: upsert one schema-v1 concept fable into the catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    # scripts/ -> concept-fable-gallery/ -> skills/ -> .codex/ -> repo root
    return Path(__file__).resolve().parents[4]


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"cannot read payload file: {exc}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        _fail(f"payload is not valid JSON: {exc}")
    if not isinstance(data, dict):
        _fail("payload must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upsert one concept fable into data/concept_fables.json"
    )
    parser.add_argument(
        "payload",
        type=str,
        help="UTF-8 JSON payload file path",
    )
    parser.add_argument(
        "--catalog",
        type=str,
        default=None,
        help="Catalog JSON path (default: <repo>/data/concept_fables.json)",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override date YYYY-MM-DD for deterministic tests",
    )
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from concept_fables.catalog import (
            CATALOG_PATH,
            load_catalog,
            normalize_concept,
            save_catalog,
            upsert_concept,
        )
    except Exception as exc:  # pragma: no cover - import path failure
        _fail(f"cannot import concept_fables.catalog: {exc}")

    payload_path = Path(args.payload)
    catalog_path = Path(args.catalog) if args.catalog else Path(CATALOG_PATH)
    payload = _load_payload(payload_path)

    try:
        catalog = load_catalog(catalog_path)
        updated, action = upsert_concept(catalog, payload, today=args.today)
        save_catalog(updated, catalog_path)
    except ValueError as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"catalog I/O failed: {exc}")

    item_id = ""
    concept = payload.get("concept", "")
    if isinstance(concept, str) and concept.strip():
        target = normalize_concept(concept)
        for item in updated["items"]:
            if normalize_concept(item.get("concept", "")) == target:
                item_id = item.get("id", "")
                break
    if not item_id and updated["items"]:
        item_id = updated["items"][-1].get("id", "")

    result = {
        "action": action,
        "id": item_id,
        "catalog": str(catalog_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
