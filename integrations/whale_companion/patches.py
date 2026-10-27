"""Small, version-guarded compatibility fixes for the pinned BiliBot build."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS_HASH = "b5c03070626dabea0ba812d89e06f2b9889a0db9c0aed2cd7941286a01922dda"
MEMORY_HASH = "3ddfad2b8b4de519a4c79e00cb7e3de4de1955ccb39a52c6e36bb0fc37856d47"

TOOLS_OLD = '            results = await plugin._search_memories(keyword, limit=5, memory_types={"video"}, score_threshold=0.5)'
TOOLS_NEW = ('            results = search_watched_videos(plugin, keyword, limit=5)\n'
             '            if not results:\n' + TOOLS_OLD.replace('            results', '                results', 1))
MEMORY_OLD = '''                lines.append(
                    f"  [{item.get('time', '?').split(' ', 1)[-1]}] 「{item.get('title', '?')[:30]}」"
                    f"{item.get('score', '?')}分 {item.get('mood', '?')} {item.get('review', '')[:40]}"
                )'''
MEMORY_NEW = '                lines.append(format_watch_item(item))'


def apply_patches(root):
    root = Path(root)
    core = root / "state/data/plugins/astrbot_plugin_bilibili_ai_bot/core"
    specs = [
        (core / "tools.py", TOOLS_HASH,
         'from .runtime import ActionRequest, EventPriority',
         'from .runtime import ActionRequest, EventPriority\nfrom .whale_recall import search_watched_videos',
         TOOLS_OLD, TOOLS_NEW),
        (core / "memory_api.py", MEMORY_HASH,
         'from .security import readable_scopes',
         'from .security import readable_scopes\nfrom .whale_recall import format_watch_item',
         MEMORY_OLD, MEMORY_NEW),
    ]
    changes = []
    for path, expected, old_import, new_import, old, new in specs:
        raw = path.read_bytes()
        source = raw.decode("utf-8").replace("\r\n", "\n")
        if new_import in source and new in source:
            continue
        if hashlib.sha256(raw).hexdigest() != expected or source.count(old) != 1:
            raise RuntimeError(f"Unexpected BiliBot source: {path.name}; inspect before patching.")
        changes.append((path, raw, source.replace(old_import, new_import, 1).replace(old, new, 1)))
    backup = root / "backups/bili-recall-compat-v1"
    if changes:
        backup.mkdir(parents=True, exist_ok=True)
    for path, raw, source in changes:
        original = backup / path.name
        if not original.exists():
            original.write_bytes(raw)
        path.write_text(source, encoding="utf-8", newline="\n")
    helper = core / "whale_recall.py"
    expected_helper = (HERE / "bili_recall_compat.py").read_bytes()
    if not helper.exists() or helper.read_bytes() != expected_helper:
        helper.write_bytes(expected_helper)
    return len(changes)
