"""Read-only catalog helpers for the M21 Awesome Design MD page."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT / "assets" / "awesome-design-md"
DESIGN_ROOT = REPOSITORY_ROOT / "design-md"
_TOP_LEVEL_METADATA_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$")
_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return simple top-level YAML frontmatter and the Markdown body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}, text

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        match = _TOP_LEVEL_METADATA_RE.match(line)
        if match and not line.startswith((" ", "\t")):
            metadata[match.group(1)] = _unquote(match.group(2))
    body = "\n".join(lines[end + 1 :]).strip()
    return metadata, body


def _display_name(slug: str, metadata: dict[str, str]) -> str:
    name = metadata.get("name", "").strip()
    if name:
        return name.removesuffix("-design-analysis")
    return slug.replace("-", " ").replace("_", " ").title()


def discover_designs(root: Path = REPOSITORY_ROOT) -> list[dict[str, Any]]:
    """Discover brand folders containing a DESIGN.md without changing the source."""
    design_root = Path(root) / "design-md"
    if not design_root.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for folder in sorted(design_root.iterdir(), key=lambda item: item.name.casefold()):
        design_path = folder / "DESIGN.md"
        if not folder.is_dir() or not design_path.is_file():
            continue
        metadata, _body = split_frontmatter(design_path.read_text(encoding="utf-8"))
        readme_path = folder / "README.md"
        records.append(
            {
                "slug": folder.name,
                "title": _display_name(folder.name, metadata),
                "description": metadata.get("description", ""),
                "design_path": design_path,
                "readme_path": readme_path if readme_path.is_file() else None,
            }
        )
    return records


def load_design_document(record: dict[str, Any]) -> tuple[dict[str, str], str]:
    """Load one selected DESIGN.md and return metadata plus Markdown body."""
    path = Path(record["design_path"])
    return split_frontmatter(path.read_text(encoding="utf-8"))


def load_readme(record: dict[str, Any]) -> str:
    """Load the optional source README for one selected design system."""
    path = record.get("readme_path")
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8").strip()


def heading_names(body: str) -> list[str]:
    """Return the main section names used for a compact page summary."""
    return [match.group(1).strip() for match in _HEADING_RE.finditer(body)]
