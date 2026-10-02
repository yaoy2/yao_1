"""Local, calibrated Windows UI Automation reader; no chat-send operations.

Nothing imports pywinauto or touches the desktop until an instance method is
called. The UI profile is produced on the destination PC from observed controls;
this module deliberately contains no DingTalk automation IDs.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time as daytime, timedelta
import hashlib
import json
import ntpath
import re
import sys
import time
from typing import Any, Callable


class DesktopError(RuntimeError):
    """A safe desktop read cannot be completed with the current profile/session."""


@dataclass(frozen=True)
class TimeEvidence:
    timestamp: datetime | None
    day: date | None
    explicit_date: bool
    precision: str = "unknown"


def parse_ui_time(
    label: str,
    cutoff: datetime,
    context_day: date | None = None,
    *,
    allow_today_clock: bool = False,
) -> TimeEvidence:
    """Parse a dedicated time control, never infer today's date from a clock.

    Bare clocks can inherit a preceding explicit date separator. The exception
    for conversation-list clocks requires a separate local calibration choice.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must include a timezone")
    text = re.sub(r"\s+", " ", str(label or "")).strip()
    if not text:
        return TimeEvidence(None, None, False)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", text):
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=cutoff.tzinfo) if stamp.tzinfo is None else stamp.astimezone(cutoff.tzinfo)
            return TimeEvidence(stamp, stamp.date(), True, "second" if text[16:17] == ":" else "minute")
        except ValueError:
            return TimeEvidence(None, None, False)
    day = None
    explicit = False
    date_match = re.search(r"(?<!\d)(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?(?!\d)", text)
    remainder = text
    if date_match:
        try:
            day = date(*(int(part) for part in date_match.groups()))
        except ValueError:
            return TimeEvidence(None, None, False)
        explicit = True
        remainder = text[:date_match.start()] + text[date_match.end():]
    else:
        relative = re.search(r"今天|今日|昨天|昨日|\bToday\b|\bYesterday\b", text, re.IGNORECASE)
        if relative:
            day = cutoff.date() - timedelta(days=int(relative.group().lower() in {"昨天", "昨日", "yesterday"}))
            explicit = True
            remainder = text[:relative.start()] + text[relative.end():]
    clock = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)", remainder)
    if clock:
        leftover = remainder[:clock.start()] + remainder[clock.end():]
    else:
        leftover = remainder
    leftover = re.sub(r"星期[一二三四五六日天]|周[一二三四五六日天]|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\b", "", leftover, flags=re.IGNORECASE)
    leftover = re.sub(r"上午|下午|晚上|凌晨|中午|早上|\bAM\b|\bPM\b|[\s,，()（）]", "", leftover, flags=re.IGNORECASE)
    if leftover:
        return TimeEvidence(None, None, False)
    if not clock:
        return TimeEvidence(None, day, explicit, "date" if day else "unknown")
    hour, minute = int(clock.group(1)), int(clock.group(2))
    second = int(clock.group(3) or 0)
    if re.search(r"下午|晚上|\bPM\b", remainder, re.IGNORECASE) and hour < 12:
        hour += 12
    if re.search(r"上午|凌晨|\bAM\b", remainder, re.IGNORECASE) and hour == 12:
        hour = 0
    if "中午" in remainder:
        if hour == 1:
            hour = 13
        elif hour not in {11, 12, 13}:
            return TimeEvidence(None, None, False)
    try:
        clock_value = daytime(hour, minute, second)
    except ValueError:
        return TimeEvidence(None, None, False)
    day = day or context_day or (cutoff.date() if allow_today_clock else None)
    stamp = datetime.combine(day, clock_value, cutoff.tzinfo) if day else None
    return TimeEvidence(stamp, day, explicit, "second" if clock.group(3) else "minute")


def merge_ordered_pages(
    existing: list[dict], page: list[dict], *, prepend: bool, key: Callable[[dict], Any]
) -> tuple[list[dict], str | None]:
    """Merge an overlapping UI viewport without text-set deduplication.

    Ambiguous overlap keeps both copies and marks the result partial. This can
    overcount an uncertain boundary, but cannot silently erase repeated messages.
    """
    missing_identity = any("_rid" in item and not item["_rid"] for item in existing + page)
    if not existing:
        return list(page), "记录缺少 UIA RuntimeId，跨屏身份无法验证" if missing_identity else None
    if not page:
        return list(existing), None
    left, right = (page, existing) if prepend else (existing, page)
    if missing_identity:
        return left + right, "记录缺少 UIA RuntimeId，保留跨屏可能重复项并标记不完整"
    a, b = [key(item) for item in left], [key(item) for item in right]
    overlaps = [length for length in range(1, min(len(a), len(b)) + 1) if a[-length:] == b[:length]]
    if not overlaps:
        return left + right, "相邻页面没有可验证的重叠，可能漏读或列表发生变化"
    if len(overlaps) != 1:
        return left + right, "相邻页面的重复记录无法唯一对齐，保留可能重复项并标记不完整"
    return left + right[overlaps[0]:], None


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


def _unique_issues(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


class DingTalkDesktop:
    """A calibrated reader for one existing, unlocked DingTalk main window."""

    _FIELDS = {"control_type", "auto_id", "class_name", "title"}
    _REQUIRED = ("scope_indicator", "conversation_list", "conversation_row", "conversation_title", "conversation_activity", "chat_header", "message_list", "message_row", "message_text")

    def __init__(self, config: dict):
        self.config = config
        self.ui = config.get("ui") or {}
        self._window = None
        self._pid = None
        self._handle = None
        self._desktop = None
        self._cutoff: datetime | None = None
        self._expected_chat: str | None = None
        self._tree_limit = max(100, min(int(self.ui.get("max_tree_nodes", 1800)), 5000))
        self._page_limit = max(1, min(int(self.ui.get("max_pages", 400)), 2000))
        self._settle = max(0.1, min(float(self.ui.get("settle_seconds", 0.4)), 3.0))

    @staticmethod
    def _assert_unlocked() -> None:
        if sys.platform != "win32":
            raise DesktopError("桌面采集仅支持 Windows；请在电脑 L 的已登录桌面运行")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        desktop = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if not desktop:
            raise DesktopError("当前桌面不可访问，可能已锁屏、注销或远程会话断开")
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            if not user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed)) or name.value.casefold() != "default":
                raise DesktopError("当前不是已解锁的交互桌面，已停止读取")
        finally:
            user32.CloseDesktop(desktop)

    @staticmethod
    def _process_name(pid: int) -> str:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        process = kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return ""
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            return ntpath.basename(path.value) if kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)) else ""
        finally:
            kernel32.CloseHandle(process)

    @staticmethod
    def _metadata(node) -> dict:
        info = node.element_info
        return {"control_type": str(info.control_type or ""), "auto_id": str(info.automation_id or ""), "class_name": str(info.class_name or ""), "title": str(info.name or "")}

    def _connect(self, *, choose: bool = False) -> None:
        self._assert_unlocked()
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise DesktopError("缺少 pywinauto；请先在项目目录运行 setup.ps1") from exc
        self._desktop = Desktop(backend="uia")
        profile = self.ui.get("window") or {}
        names = profile.get("process_names", ["DingTalk.exe"])
        if not isinstance(names, list) or not names or any(str(item).casefold() != "dingtalk.exe" for item in names):
            raise DesktopError("窗口进程必须是经校验的 DingTalk.exe；不允许匹配其他应用")
        candidates = []
        try:
            for window in self._desktop.windows():
                pid = int(window.element_info.process_id)
                if self._process_name(pid).casefold() not in {name.casefold() for name in names}:
                    continue
                if not window.is_visible():
                    continue
                metadata = self._metadata(window)
                if any(metadata.get(field) != str(profile[field]) for field in self._FIELDS if field in profile):
                    continue
                candidates.append(window)
        except Exception as exc:
            raise DesktopError("无法读取钉钉窗口；请保持钉钉在普通权限的已解锁桌面") from exc
        if choose and len(candidates) > 1:
            print("检测到多个钉钉窗口。以下信息仅显示在本机：")
            for index, window in enumerate(candidates, 1):
                print(f"[{index}] {self._metadata(window)}")
            selection = input("选择聊天主窗口编号：").strip()
            if not selection.isdigit() or not 1 <= int(selection) <= len(candidates):
                raise DesktopError("未选择有效的钉钉主窗口")
            candidates = [candidates[int(selection) - 1]]
        if len(candidates) != 1:
            raise DesktopError(f"需唯一可见的钉钉主窗口，当前匹配 {len(candidates)} 个；请关闭钉钉弹窗或重新校准")
        self._window = candidates[0]
        self._pid = int(self._window.element_info.process_id)
        self._handle = int(self._window.element_info.handle)
        self._assert_window()

    def _assert_window(self) -> None:
        self._assert_unlocked()
        if self._cutoff and datetime.now(self._cutoff.tzinfo).date() != self._cutoff.date():
            raise DesktopError("采集已跨日或所选日期不是今天；停止解释相对日期")
        if self._window is None:
            raise DesktopError("尚未连接钉钉窗口")
        try:
            if int(self._window.element_info.process_id) != self._pid or int(self._window.element_info.handle) != self._handle or not self._window.is_visible():
                raise DesktopError("钉钉窗口已变化或不可见，已停止读取")
            if self._process_name(self._pid).casefold() != "dingtalk.exe":
                raise DesktopError("窗口进程已变化，已停止读取")
            metadata = self._metadata(self._window)
            if any(metadata.get(field) != str(self.ui.get("window", {})[field]) for field in self._FIELDS if field in self.ui.get("window", {})):
                raise DesktopError("钉钉主窗口与校准配置不一致")
        except DesktopError:
            raise
        except Exception as exc:
            raise DesktopError("钉钉窗口已失效，需重新打开聊天主窗口") from exc

    def _assert_control(self, node) -> None:
        self._assert_window()
        try:
            if int(node.element_info.process_id) != self._pid or int(node.top_level_parent().element_info.handle) != self._handle:
                raise DesktopError("控件不再属于已确认的钉钉主窗口")
        except DesktopError:
            raise
        except Exception as exc:
            raise DesktopError("钉钉控件已失效；没有继续点击或滚动") from exc

    @staticmethod
    def _runtime_id(node) -> str:
        try:
            runtime_id = node.element_info.runtime_id
            return ":".join(map(str, runtime_id)) if runtime_id else ""
        except Exception:
            return ""

    def _tree(self, root, *, max_depth: int = 14) -> tuple[list[dict], bool]:
        queue = deque([(root, 0, None)])
        rows = []
        truncated = False
        while queue and len(rows) < self._tree_limit:
            node, depth, parent = queue.popleft()
            try:
                metadata = self._metadata(node)
                item = {"number": len(rows) + 1, "parent": parent, "depth": depth, "node": node, **metadata}
                rows.append(item)
                children = node.children()
                if depth >= max_depth:
                    truncated = truncated or bool(children)
                else:
                    queue.extend((child, depth + 1, item["number"]) for child in children)
            except Exception as exc:
                raise DesktopError("读取控件树失败；钉钉页面可能已变化") from exc
        return rows, truncated or bool(queue)

    @classmethod
    def _check_selector(cls, selector: dict) -> None:
        if not isinstance(selector, dict) or not selector:
            raise DesktopError("控件选择器为空或格式错误，请重新校准")
        if selector == {"self": True}:
            return
        if set(selector) == {"path"} and isinstance(selector["path"], list) and selector["path"]:
            for step in selector["path"]:
                cls._check_selector(step)
                if "path" in step or "self" in step:
                    raise DesktopError("控件路径只允许稳定属性，不允许索引或嵌套路径")
            return
        if not set(selector) <= cls._FIELDS or not selector.get("control_type"):
            raise DesktopError("控件选择器须使用 control_type 和观察得到的属性，不能使用数组索引")
        if any(not isinstance(value, str) or not value for value in selector.values()):
            raise DesktopError("控件选择器属性必须是非空文字")

    def _matches(self, node, selector: dict) -> bool:
        return all(self._metadata(node).get(key) == value for key, value in selector.items())

    def _find(self, root, selector: dict) -> list:
        self._check_selector(selector)
        if selector == {"self": True}:
            return [root]
        if "path" in selector:
            nodes = [root]
            for step in selector["path"]:
                nodes = [child for parent in nodes for child in parent.children() if self._matches(child, step)]
                if len(nodes) > self._tree_limit:
                    raise DesktopError("选择器匹配数量超过上限，请缩小控件范围")
            return nodes
        tree, truncated = self._tree(root)
        if truncated:
            raise DesktopError("控件树超过诊断上限，无法证明选择器匹配唯一")
        return [row["node"] for row in tree[1:] if self._matches(row["node"], selector)]

    def _one(self, root, role: str):
        selector = self.ui.get(role)
        if not selector:
            raise DesktopError(f"缺少 {role} 校准，请在电脑 L 运行 calibrate")
        result = self._find(root, selector)
        if len(result) != 1:
            raise DesktopError(f"{role} 应唯一匹配，实际匹配 {len(result)} 个控件")
        self._assert_control(result[0])
        return result[0]

    def _field(self, root, role: str, *, many: bool = False) -> str:
        selector = self.ui.get(role)
        if not selector:
            return ""
        nodes = self._find(root, selector)
        if not many and len(nodes) > 1:
            raise DesktopError(f"{role} 匹配多个控件，无法确认消息字段")
        nodes.sort(key=self._position)
        return "\n".join(str(node.window_text() or "").strip() for node in nodes).strip()

    def _assert_scope(self) -> None:
        node = self._one(self._window, "scope_indicator")
        if not node.is_visible() or str(node.window_text() or "").strip() != self.ui.get("scope_expected"):
            raise DesktopError("当前会话筛选范围与校准的全部会话不一致，已停止扫描")
        try:
            state = self.ui.get("scope_state")
            selected = bool(node.iface_selection_item.CurrentIsSelected) if state == "selection" else int(node.iface_toggle.CurrentToggleState) == 1 if state == "toggle" else False
        except Exception as exc:
            raise DesktopError("无法复核全部会话筛选状态，请重新校准") from exc
        if not selected:
            raise DesktopError("全部会话筛选未被选中，已停止扫描")

    def _assert_chat(self) -> None:
        self._assert_window()
        if not self._expected_chat or str(self._one(self._window, "chat_header").window_text() or "").strip() != self._expected_chat:
            raise DesktopError("采集中当前聊天发生变化，已丢弃未核对页面并停止读取")

    @staticmethod
    def _position(node) -> tuple[int, int]:
        try:
            rectangle = node.rectangle()
            return int(rectangle.top), int(rectangle.left)
        except Exception as exc:
            raise DesktopError("控件没有可用位置，无法确认消息先后顺序") from exc

    def _visible_rows(self, container, role: str) -> list:
        bounds = container.rectangle()
        result = []
        for node in self._find(container, self.ui[role]):
            rectangle = node.rectangle()
            if node.is_visible() and rectangle.bottom > bounds.top and rectangle.top < bounds.bottom and rectangle.right > bounds.left and rectangle.left < bounds.right:
                result.append(node)
        result.sort(key=self._position)
        return result

    def _scroll_state(self, container) -> tuple[bool, float]:
        self._assert_control(container)
        try:
            pattern = container.iface_scroll
            scrollable = bool(pattern.CurrentVerticallyScrollable)
            percent = float(pattern.CurrentVerticalScrollPercent)
            if scrollable and not 0 <= percent <= 100:
                raise DesktopError("滚动控件未提供真实位置，无法证明已翻到边界")
            return scrollable, percent
        except DesktopError:
            raise
        except Exception as exc:
            raise DesktopError("此列表未暴露 UIA ScrollPattern，无法安全自动翻页；需更换可访问的列表控件或钉钉版本") from exc

    def _move_scroll(self, container, *, edge: float | None = None, direction: int = 0) -> None:
        self._assert_control(container)
        scrollable, _ = self._scroll_state(container)
        if not scrollable:
            return
        try:
            if edge is not None:
                container.iface_scroll.SetScrollPercent(-1.0, edge)
            else:
                container.iface_scroll.Scroll(2, 4 if direction > 0 else 1)  # NoAmount, SmallIncrement/Decrement
        except Exception as exc:
            raise DesktopError("UIA 翻页失败，未使用键盘或坐标点击替代") from exc
        time.sleep(self._settle)
        self._assert_control(container)

    def inspect(self) -> dict:
        self._connect()
        rows, truncated = self._tree(self._window, max_depth=12)
        return {"local_private_data": True, "window": self._metadata(self._window), "truncated": truncated, "nodes": [{key: value for key, value in row.items() if key != "node"} for row in rows]}

    def doctor(self) -> dict:
        if any(not self.ui.get(role) for role in self._REQUIRED):
            missing = [role for role in self._REQUIRED if not self.ui.get(role)]
            raise DesktopError("缺少本机校准角色：" + ", ".join(missing))
        if not self.ui.get("message_time") and not self.ui.get("date_separator"):
            raise DesktopError("必须配置消息时间或明确日期分隔控件")
        if not self.ui.get("conversation_list_scope_confirmed") or self.ui.get("message_order") != "oldest_first":
            raise DesktopError("尚未确认完整会话列表范围和消息先后顺序，请重新校准")
        if not self.ui.get("conversation_kind") or not self.ui.get("direct_labels") or not self.ui.get("group_labels"):
            raise DesktopError("单聊和群聊类型标记未完整校准，尚不能启用自动任务")
        if set(self.ui["direct_labels"]) & set(self.ui["group_labels"]):
            raise DesktopError("单聊和群聊类型标记重叠，无法确认采集对象")
        if not (self.ui.get("message_sender") and self.config.get("self_names")) and not (self.ui.get("message_self") and self.ui.get("self_labels") and self.ui.get("other_labels")):
            raise DesktopError("缺少可确认发言者/本人身份的字段，无法区分群内本人消息")
        self._connect()
        self._assert_scope()
        warnings = []
        for container_role, row_role, fields in (
            ("conversation_list", "conversation_row", ("conversation_title", "conversation_activity")),
            ("message_list", "message_row", ("message_text",)),
        ):
            container = self._one(self._window, container_role)
            self._scroll_state(container)
            rows = self._visible_rows(container, row_role)
            if not rows:
                raise DesktopError(f"{row_role} 没有可读样例；请手工打开一个有消息的聊天后重试")
            if row_role == "conversation_row":
                try:
                    rows[0].iface_selection_item
                except Exception as exc:
                    raise DesktopError("会话行不支持 UIA SelectionItem，无法安全打开；请重新校准会话行") from exc
            for role in fields:
                if not any(self._field(row, role, many=role == "message_text") for row in rows):
                    raise DesktopError(f"{role} 没有可读文字，请重新选择控件")
        if not self._one(self._window, "chat_header").window_text().strip():
            raise DesktopError("当前聊天标题为空，无法核对打开对象")
        warnings.extend(self.ui.get("scope_limitations", []))
        return {"ready": True, "backend": "uia", "process": "DingTalk.exe", "warnings": warnings}

    def _show_tree(self, root) -> list[dict]:
        rows, truncated = self._tree(root, max_depth=12)
        for row in rows:
            title = row["title"].replace("\n", " ")[:90]
            print(f"[{row['number']}] {'  ' * min(row['depth'], 8)}{row['control_type']} id={row['auto_id']!r} class={row['class_name']!r} text={title!r}")
        if truncated:
            print("（本次树显示已截断；可选择已显示的更小容器继续，不可用截断结果证明完整。）")
        return rows

    @staticmethod
    def _choose_node(rows: list[dict], label: str, *, optional: bool = False):
        suffix = "，没有可验证控件填 0" if optional else ""
        value = input(f"选择{label}的编号{suffix}：").strip()
        if optional and value == "0":
            return None
        if not value.isdigit() or not 1 <= int(value) <= len(rows):
            raise DesktopError("控件编号无效；本次未保存配置")
        return rows[int(value) - 1]["node"]

    def _stable_selector(self, root, target, *, repeated: bool = False) -> dict:
        if self._runtime_id(root) == self._runtime_id(target) and self._runtime_id(root):
            return {"self": True}
        metadata = self._metadata(target)
        if not metadata["control_type"]:
            raise DesktopError("所选控件没有稳定类型")
        base = {"control_type": metadata["control_type"]}
        if metadata["class_name"]:
            base["class_name"] = metadata["class_name"]
        if metadata["auto_id"] and not repeated:
            candidate = {"control_type": metadata["control_type"], "auto_id": metadata["auto_id"]}
            try:
                if len(self._find(root, candidate)) == 1:
                    return candidate
            except DesktopError:
                pass  # A bounded direct-child path may still be verifiable.
        if not repeated:
            try:
                if len(self._find(root, base)) == 1:
                    return base
            except DesktopError:
                pass
        rows, truncated = self._tree(root)
        target_id = self._runtime_id(target)
        located = next((item for item in rows if self._runtime_id(item["node"]) == target_id and target_id), None)
        if not located:
            raise DesktopError("所选控件不在要求的容器内，请重新选择")
        path = []
        while located["parent"] is not None:
            step = {"control_type": located["control_type"]}
            if located["class_name"]:
                step["class_name"] = located["class_name"]
            if located["auto_id"] and (not repeated or path):
                step["auto_id"] = located["auto_id"]
            path.append(step)
            located = rows[located["parent"] - 1]
        selector = {"path": list(reversed(path))}
        matches = self._find(root, selector)
        if (not repeated and len(matches) != 1) or not matches:
            raise DesktopError("此字段没有可区分的稳定属性；不能以位置索引保存，请选择有独立 UIA 属性的控件")
        return selector

    def calibrate(self) -> dict:
        print("校准只在当前电脑读取钉钉；样例可能含私人聊天文字，不应上传或提交。")
        input("请先手工打开钉钉完整会话列表，并打开一个包含今日消息的单聊；完成后按回车：")
        self._connect(choose=True)
        window_meta = self._metadata(self._window)
        profile: dict = {"window": {"process_names": ["DingTalk.exe"], "control_type": window_meta["control_type"], "class_name": window_meta["class_name"], "title": window_meta["title"]}, "message_order": "oldest_first"}
        profile["window"] = {key: value for key, value in profile["window"].items() if value}
        tree = self._show_tree(self._window)
        scope = self._choose_node(tree, "全部会话筛选的选中状态控件（必须提供 Selection 或 Toggle）")
        profile["scope_indicator"] = self._stable_selector(self._window, scope)
        profile["scope_expected"] = str(scope.window_text() or "").strip()
        try:
            profile["scope_state"] = "selection" if scope.iface_selection_item.CurrentIsSelected else ""
        except Exception:
            profile["scope_state"] = ""
        if not profile["scope_state"]:
            try:
                profile["scope_state"] = "toggle" if scope.iface_toggle.CurrentToggleState == 1 else ""
            except Exception:
                pass
        if not profile["scope_state"]:
            raise DesktopError("所选筛选控件没有可读取的选中状态，不能仅凭存在全部标签确认范围")
        if not profile["scope_expected"]:
            raise DesktopError("筛选状态控件没有可核对的文字")
        conversation_list = self._choose_node(tree, "完整会话列表容器（需要 ScrollPattern）")
        profile["conversation_list"] = self._stable_selector(self._window, conversation_list)
        self._scroll_state(conversation_list)
        list_tree = self._show_tree(conversation_list)
        sample_row = self._choose_node(list_tree, "一个会话整行，不选标题文字")
        profile["conversation_row"] = self._stable_selector(conversation_list, sample_row, repeated=True)
        row_tree = self._show_tree(sample_row)
        for role, label, optional in (("conversation_title", "会话名称", False), ("conversation_activity", "最近消息日期/时间", False), ("conversation_kind", "单聊/群聊类型文字", True)):
            node = self._choose_node(row_tree, label, optional=optional)
            if node is not None:
                profile[role] = self._stable_selector(sample_row, node)
        self.ui = profile
        if profile.get("conversation_kind"):
            print("当前可见会话的类型样例：")
            for row in self._visible_rows(conversation_list, "conversation_row"):
                print(f"  {self._field(row, 'conversation_title')!r}: {self._field(row, 'conversation_kind')!r}")
            profile["direct_labels"] = [item.strip() for item in input("人工核对后，输入明确表示单聊的类型文字，多个用 | 分开；无可靠标记留空：").split("|") if item.strip()]
            profile["group_labels"] = [item.strip() for item in input("输入明确表示群聊的类型文字，多个用 | 分开；无可靠标记留空：").split("|") if item.strip()]
            if set(profile["direct_labels"]) & set(profile["group_labels"]):
                raise DesktopError("单聊和群聊类型标记不能重叠")
        profile["activity_time_only_is_today"] = input("已人工确认会话列表中孤立 HH:mm 只表示今天？输入 YES 才启用：").strip() == "YES"
        profile["conversation_list_scope_confirmed"] = input("已确认该列表含全部聊天（包括置顶和免打扰），不是未读/筛选分组？输入 YES：").strip() == "YES"
        if not profile["conversation_list_scope_confirmed"]:
            raise DesktopError("未确认完整会话列表，本次不保存校准")
        profile["scope_limitations"] = []
        if input("已确认此视图也能展示归档/隐藏会话，且分组全部展开？不能确认填 NO，确认填 YES：").strip() != "YES":
            profile["scope_limitations"].append("界面未展示的折叠、隐藏或归档会话无法验证；其他单聊范围可能不完整")
        header = self._choose_node(tree, "当前聊天标题（须只包含精确会话名）")
        profile["chat_header"] = self._stable_selector(self._window, header)
        message_list = self._choose_node(tree, "聊天消息列表容器（需要 ScrollPattern）")
        profile["message_list"] = self._stable_selector(self._window, message_list)
        self._scroll_state(message_list)
        message_tree = self._show_tree(message_list)
        message_row = self._choose_node(message_tree, "一条完整消息的外层控件")
        profile["message_row"] = self._stable_selector(message_list, message_row, repeated=True)
        detail_tree = self._show_tree(message_row)
        for role, label, optional in (("message_text", "该条消息正文", False), ("message_sender", "发送者姓名", True), ("message_time", "消息日期/时间", True), ("message_self", "明确表示本人/对方的标记（没有填 0）", True), ("message_kind", "明确表示文字/图片/附件的类型标记", True)):
            node = self._choose_node(detail_tree, label, optional=optional)
            if node is not None:
                profile[role] = self._stable_selector(message_row, node)
        if profile.get("message_self"):
            profile["self_labels"] = [item.strip() for item in input("明确表示本人发言的标记文字，多个用 | 分开：").split("|") if item.strip()]
            profile["other_labels"] = [item.strip() for item in input("明确表示对方发言的标记文字，多个用 | 分开；没有留空：").split("|") if item.strip()]
            if set(profile["self_labels"]) & set(profile["other_labels"]):
                raise DesktopError("本人和对方标记不能重叠")
        if profile.get("message_kind"):
            for kind, label in (("text", "纯文字"), ("image", "图片"), ("attachment", "附件")):
                profile[f"{kind}_labels"] = [item.strip() for item in input(f"明确表示{label}消息的类型文字，多个用 | 分开；没有留空：").split("|") if item.strip()]
            labels = [label for kind in ("text", "image", "attachment") for label in profile[f"{kind}_labels"]]
            if len(labels) != len(set(labels)):
                raise DesktopError("不同消息类型的标记不能重叠")
        separator = self._choose_node(message_tree, "明确日期分隔文字（如今天/2026年10月2日）", optional=True)
        if separator is not None:
            profile["date_separator"] = self._stable_selector(message_list, separator, repeated=True)
        if input("已确认消息从上到下由旧到新，所选消息行覆盖双方消息？输入 YES：").strip() != "YES":
            raise DesktopError("未确认消息顺序和双方消息范围，本次不保存校准")
        self.ui = profile
        print("校准样例（仅本机显示）：")
        print(json.dumps({"title": header.window_text(), "conversation": {role: self._field(sample_row, role) for role in ("conversation_title", "conversation_activity", "conversation_kind")}, "message": {role: self._field(message_row, role, many=role == "message_text") for role in ("message_text", "message_sender", "message_time", "message_self")}}, ensure_ascii=False, indent=2))
        if input("核对字段含义和文字正确后输入 YES 保存；任意其他输入取消：").strip() != "YES":
            raise DesktopError("用户取消校准，本次未保存配置")
        return profile

    def _conversation_page(self, container) -> list[dict]:
        self._assert_scope()
        result = []
        for node in self._visible_rows(container, "conversation_row"):
            title = self._field(node, "conversation_title")
            activity = self._field(node, "conversation_activity")
            label = self._field(node, "conversation_kind")
            kind = "direct" if label and label in self.ui.get("direct_labels", []) else "group" if label and label in self.ui.get("group_labels", []) else "unknown"
            result.append({"title": title, "activity": activity, "kind": kind, "_rid": self._runtime_id(node), "_node": node})
        return result

    def _message_page(self, container) -> list[dict]:
        self._assert_chat()
        entries = []
        for node in self._visible_rows(container, "message_row"):
            sender = self._field(node, "message_sender")
            self_label = self._field(node, "message_self")
            self_names = set(self.config.get("self_names") or [])
            is_self = True if self_label and self_label in self.ui.get("self_labels", []) else False if self_label and self_label in self.ui.get("other_labels", []) else (sender in self_names if sender and self_names else None)
            text = self._field(node, "message_text", many=True)
            kind_label = self._field(node, "message_kind")
            kind = next((kind for kind in ("attachment", "image", "text") if kind_label and kind_label in self.ui.get(f"{kind}_labels", [])), "unknown")
            entries.append({"_rid": self._runtime_id(node), "_position": self._position(node), "_separator": False, "_time": self._field(node, "message_time"), "sender": sender, "is_self": is_self, "text": text, "kind": kind})
        if self.ui.get("date_separator"):
            message_ids = {entry["_rid"] for entry in entries if entry["_rid"]}
            for node in self._visible_rows(container, "date_separator"):
                if self._runtime_id(node) in message_ids:
                    continue
                entries.append({"_rid": self._runtime_id(node), "_position": self._position(node), "_separator": True, "_time": str(node.window_text() or "").strip()})
        entries.sort(key=lambda entry: entry["_position"])
        self._assert_chat()
        return entries

    @staticmethod
    def _page_key(item: dict):
        fields = {key: value for key, value in item.items() if key not in {"_node", "_position"}}
        return _digest(fields)

    def _scan(self, container, reader: Callable, *, upwards: bool = False, stop_on_older: bool = False) -> tuple[list[dict], bool, list[str]]:
        issues = []
        entries = []
        seen_runtime = {}
        self._move_scroll(container, edge=100.0 if upwards else 0.0)
        scrollable, initial_position = self._scroll_state(container)
        if scrollable and abs(initial_position - (100.0 if upwards else 0.0)) > 0.001:
            issues.append("列表未到已请求的起始边界，可能遗漏起始记录")
        stalled = 0
        previous_keys = None
        previous_position = None
        for _ in range(self._page_limit):
            self._assert_control(container)
            page = reader(container)
            keys = [self._page_key(item) for item in page]
            scrollable, position = self._scroll_state(container)
            missing_identity = any(not item.get("_rid") for item in page)
            for item in page:
                rid = item.get("_rid")
                body = {key: value for key, value in item.items() if key not in {"_rid", "_node", "_position"}}
                if rid and rid in seen_runtime and seen_runtime[rid] != _digest(body):
                    issues.append("控件被虚拟化复用或内容在采集中变化，不能证明没有遗漏")
                if rid:
                    seen_runtime[rid] = _digest(body)
            if previous_keys != keys or (missing_identity and previous_position != position):
                entries, overlap_issue = merge_ordered_pages(entries, page, prepend=upwards, key=self._page_key)
                if overlap_issue:
                    issues.append(overlap_issue)
            if previous_keys == keys and previous_position is not None and abs(previous_position - position) > 0.0001:
                issues.append("滚动位置变化但控件及内容完全相同，无法区分重复消息与虚拟化复用")
            at_edge = not scrollable or (position <= 0.001 if upwards else position >= 99.999)
            older = stop_on_older and any((evidence.day is not None and evidence.explicit_date and evidence.day < self._cutoff.date()) for evidence in (parse_ui_time(item.get("_time", ""), self._cutoff) for item in page))
            if at_edge or older:
                # Boundary must survive a second read; an empty viewport is never
                # evidence that a virtualized list is empty.
                time.sleep(self._settle)
                check = reader(container)
                if [self._page_key(item) for item in check] != keys:
                    issues.append("边界复核时列表仍在变化，范围无法完整确认")
                if not page:
                    issues.append("列表可见内容为空，无法区分空记录与控件未加载")
                return entries, not issues, _unique_issues(issues)
            if len(entries) > int(self.ui.get("max_records", 20000)):
                issues.append("读取记录数量达到上限，尚未证明已到日期边界")
                break
            previous_keys = keys
            previous_position = position
            self._move_scroll(container, direction=-1 if upwards else 1)
            _, after = self._scroll_state(container)
            stalled = stalled + 1 if abs(after - position) < 0.0001 else 0
            if stalled >= 2:
                issues.append("列表尚未到边界但连续滚动无进展")
                break
        else:
            issues.append("翻页次数达到上限，尚未证明已读取完整范围")
        return entries, False, _unique_issues(issues)

    def _open_conversation(self, title: str) -> None:
        container = self._one(self._window, "conversation_list")
        self._move_scroll(container, edge=0.0)
        for _ in range(self._page_limit):
            self._assert_control(container)
            matches = [item for item in self._conversation_page(container) if item["title"] == title]
            if len(matches) > 1:
                raise DesktopError("出现同名会话，无法确定应打开的对象")
            if matches:
                node = matches[0]["_node"]
                self._assert_control(node)
                if not node.is_enabled() or not node.is_visible():
                    raise DesktopError("待打开会话已不可用")
                # UIA SelectionItem selects only a verified conversation row.
                # No input-field writes, Enter presses, global wheel or fallback.
                try:
                    node.iface_selection_item.Select()
                except Exception as exc:
                    raise DesktopError("会话行不支持 UIA SelectionItem，无法安全打开；请重新选择行控件") from exc
                for _ in range(8):
                    time.sleep(self._settle)
                    self._assert_window()
                    header = str(self._one(self._window, "chat_header").window_text() or "").strip()
                    if header == title:
                        self._expected_chat = title
                        return
                raise DesktopError("打开后的聊天标题与目标不完全一致，已停止读取该对话")
            scrollable, before = self._scroll_state(container)
            if not scrollable or before >= 99.999:
                break
            self._move_scroll(container, direction=1)
            _, after = self._scroll_state(container)
            if abs(after - before) < 0.0001:
                break
        raise DesktopError("重新定位会话失败；列表可能已变化")

    def _resolve_messages(self, entries: list[dict], title: str, cutoff: datetime) -> tuple[list[dict], list[str]]:
        context_day = None
        previous_day = None
        previous_stamp = None
        messages = []
        issues = []
        for index, entry in enumerate(entries):
            evidence = parse_ui_time(entry.get("_time", ""), cutoff, context_day)
            if evidence.explicit_date and evidence.day:
                context_day = evidence.day
                if previous_day and evidence.day < previous_day:
                    issues.append("消息日期顺序与校准顺序矛盾，可能翻页错位")
                previous_day = evidence.day
            stamp = evidence.timestamp
            if stamp is not None:
                if previous_stamp is not None and stamp < previous_stamp:
                    issues.append("消息完整时间倒退，裸时钟可能跨日，已停止沿用日期上下文")
                    if not evidence.explicit_date:
                        context_day = None
                        continue
                previous_stamp = stamp
            if entry.get("_separator"):
                if not evidence.explicit_date:
                    issues.append("日期分隔控件未提供明确日期")
                continue
            if stamp is None:
                if context_day and context_day < cutoff.date():
                    continue
                issues.append("存在无法确认日期或时间的消息，未保存其正文")
                continue
            if stamp.date() != cutoff.date() or stamp > cutoff:
                continue
            if stamp + timedelta(seconds=60 if evidence.precision == "minute" else 1) > cutoff:
                issues.append("截止时刻附近消息的显示时间精度不足，未保存可能晚于截止时刻的正文")
                continue
            if not entry.get("sender") or entry.get("is_self") is None:
                issues.append("当天消息的发送者或本人归属无法确认")
            if not entry.get("text"):
                issues.append("当天消息正文不可读，可能是图片、附件或未暴露文本")
            if entry.get("kind") == "unknown":
                issues.append("当天消息类型无法确认，不能将文件名或图片替代文字视为完整正文")
            payload = {key: entry.get(key) for key in ("sender", "is_self", "text", "kind")}
            payload.update({"id": "uia-" + _digest([title, stamp.isoformat(), index, payload]), "timestamp": stamp.isoformat(), "source": "本机钉钉 UIA；已核对聊天标题和显示日期"})
            messages.append(payload)
        return messages, _unique_issues(issues)

    def collect(self, run_at: datetime) -> dict:
        if run_at.tzinfo is None or run_at.utcoffset() is None:
            raise DesktopError("采集截止时间必须包含时区")
        if not self.config.get("calibration_ok"):
            raise DesktopError("尚未完成电脑 L 的本机校准")
        self._cutoff = run_at
        self.doctor()
        capture = {"date": run_at.date().isoformat(), "cutoff": run_at.isoformat(), "discovery_complete": False, "issues": [], "conversations": []}
        try:
            rows, complete, issues = self._scan(self._one(self._window, "conversation_list"), self._conversation_page)
        except DesktopError as exc:
            capture["issues"] = [str(exc)]
            return capture
        capture["discovery_complete"] = complete
        capture["issues"].extend(issues)
        if self.ui.get("scope_limitations"):
            capture["issues"].extend(self.ui["scope_limitations"])
            capture["discovery_complete"] = False
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["title"]] = counts.get(row["title"], 0) + 1
        priority = str(self.config.get("priority_contact") or "").strip()
        group = str(self.config.get("self_group") or "").strip()
        selected = []
        for title, kind in ((priority, "direct"), (group, "group")):
            if not title:
                capture["issues"].append("指定对象尚未配置")
                capture["discovery_complete"] = False
            elif counts.get(title) != 1:
                capture["issues"].append("指定对象未唯一出现在完整会话列表，未打开同名或缺失对象")
                capture["discovery_complete"] = False
                capture["conversations"].append({"id": _digest([title, kind]), "title": title, "kind": kind, "complete": False, "issues": ["会话缺失或同名歧义"], "messages": []})
            else:
                row = next(item for item in rows if item["title"] == title)
                if row["kind"] != kind:
                    capture["issues"].append("指定对象缺少匹配的类型证据或与标记矛盾，已跳过")
                    capture["discovery_complete"] = False
                    capture["conversations"].append({"id": _digest([title, kind]), "title": title, "kind": kind, "complete": False, "issues": ["指定对象类型未确认，未打开"], "messages": []})
                else:
                    selected.append({**row, "kind": kind})
        for row in rows:
            if row["title"] in {priority, group}:
                continue
            evidence = parse_ui_time(row["activity"], run_at, allow_today_clock=bool(self.ui.get("activity_time_only_is_today")))
            if evidence.day is not None and evidence.day != run_at.date():
                continue
            if row["kind"] == "group":
                continue
            if row["kind"] == "unknown" or evidence.day is None or not row["title"] or counts[row["title"]] != 1:
                capture["issues"].append("部分会话无法确认单聊类型、当天活跃或唯一名称，已跳过")
                capture["discovery_complete"] = False
                continue
            selected.append(row)
        interrupted = False
        for row in selected:
            title, kind = row["title"], row["kind"]
            conversation = {"id": _digest([title, kind]), "title": title, "kind": kind, "complete": False, "issues": [], "messages": []}
            capture["conversations"].append(conversation)
            try:
                self._open_conversation(title)
                entries, complete, issues = self._scan(self._one(self._window, "message_list"), self._message_page, upwards=True, stop_on_older=True)
                messages, parse_issues = self._resolve_messages(entries, title, run_at)
                activity = parse_ui_time(row["activity"], run_at, allow_today_clock=bool(self.ui.get("activity_time_only_is_today")))
                if not messages and activity.timestamp is not None and activity.day == run_at.date() and activity.timestamp + timedelta(seconds=60 if activity.precision == "minute" else 1) <= run_at:
                    parse_issues.append("会话列表明确显示截止前当天活跃，但消息列表没有可确认的当天记录，不能判定今天零条")
                conversation.update(messages=messages, issues=_unique_issues(issues + parse_issues), complete=complete and not parse_issues)
            except DesktopError as exc:
                conversation["issues"].append(str(exc))
                capture["issues"].append("桌面读取中断，后续会话尚未采集")
                capture["discovery_complete"] = False
                interrupted = True
                break
        if not interrupted:
            try:
                final_rows, final_complete, final_issues = self._scan(self._one(self._window, "conversation_list"), self._conversation_page)
                snapshot = lambda items: sorted((item["title"], item["kind"], item["activity"]) for item in items)
                if not final_complete or snapshot(rows) != snapshot(final_rows):
                    capture["issues"].append("结束复查时会话列表范围、类型或最新时间变化，无法证明当天对象完整")
                    capture["discovery_complete"] = False
                capture["issues"].extend(final_issues)
            except DesktopError:
                capture["issues"].append("无法完成结束时的会话列表一致性复核")
                capture["discovery_complete"] = False
        capture["issues"] = _unique_issues(capture["issues"])
        return capture
