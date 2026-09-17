import base64
import ast
import copy
import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from utils import todo_db
from utils.todo_chat import TodoChatService, snapshot_db
from tests.test_todo_db import patched_todo_storage


class Response:
    def __init__(self, status, data):
        self.status_code, self.data = status, data

    def json(self):
        return self.data


class FakeGitHub:
    def __init__(self, records=None):
        self.content = todo_db.build_markdown_backup(records or [])
        self.writes = 0
        self.reads = 0
        self.conflict = False
        self.race_before_preflight = False

    @property
    def sha(self):
        return hashlib.sha256(self.content.encode()).hexdigest()

    def get(self, url, **kwargs):
        self.reads += 1
        if self.race_before_preflight and self.reads == 2:
            self.content += "\n"
        return Response(200, {"sha": self.sha, "content": base64.b64encode(self.content.encode()).decode()})

    def put(self, url, *, json, **kwargs):
        if self.conflict or json["sha"] != self.sha:
            return Response(409, {})
        self.content = base64.b64decode(json["content"]).decode()
        self.writes += 1
        return Response(200, {"content": {"sha": self.sha}})


def service(remote):
    return TodoChatService(environ={"GITHUB_BACKUP_TOKEN": "test-only-not-a-credential"}, session=remote)


class TodoChatTest(unittest.TestCase):
    def test_stale_page_cannot_reopen_item_completed_on_phone(self):
        with tempfile.TemporaryDirectory() as directory, patched_todo_storage(directory):
            todo_db.init_db()
            record_id = todo_db.add_todo("跨端事项")
            original = todo_db.get_todos()[0]
            st = SimpleNamespace(session_state={
                f"todo_revision_{record_id}": f"{original['uid']}:{original['updated_at']}",
                "checkbox": False}, warning=Mock())
            remote = {**original, "status": "done", "is_archived": True,
                      "updated_at": "2099-01-01 00:00:00.000001"}
            def merge():
                todo_db.import_todo_records([remote])
                return True
            namespace = {"st": st, "todo_db": todo_db, "merge_remote_todos_from_github": merge,
                         "sync_todo_backup_to_github": Mock()}
            page = Path(__file__).resolve().parents[1] / "pages/14_todos.py"
            nodes = [node for node in ast.parse(page.read_text(encoding="utf-8")).body
                     if isinstance(node, ast.FunctionDef) and node.name in {"prepare_todo_edit", "toggle_todo_done"}]
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(page), "exec"), namespace)
            namespace["toggle_todo_done"](record_id, "checkbox")
            self.assertEqual("done", todo_db.get_todos(view="all")[0]["status"])
            namespace["sync_todo_backup_to_github"].assert_not_called()
            st.warning.assert_called_once()

    def test_add_retry_and_real_m14_roundtrip(self):
        remote = FakeGitHub()
        api = service(remote)
        request_id = str(uuid.uuid4())
        result = api.add("提醒我2026-10-01下午3点交材料\n- 联系老师", request_id)
        self.assertEqual(2, result["created"])
        self.assertEqual(("2026-10-01", "15:00"), (result["items"][0]["due_date"], result["items"][0]["due_time"]))
        self.assertFalse(result["notifications"])
        again = api.add("提醒我2026-10-01下午3点交材料\n- 联系老师", request_id)
        self.assertEqual(0, again["created"])
        self.assertEqual(1, remote.writes)
        with tempfile.TemporaryDirectory() as directory, patched_todo_storage(directory):
            todo_db.init_db()
            todo_db.import_todo_records(todo_db.parse_markdown_backup(remote.content))
            self.assertEqual(2, len(todo_db.get_todos()))
            item = api.list(keyword="交材料")["items"][0]
            api.update(item["uid"], item["revision"], done=True)
            todo_db.import_todo_records(todo_db.parse_markdown_backup(remote.content))
            self.assertEqual(1, len(todo_db.get_todos()))
            self.assertEqual("done", todo_db.get_todos(view="archived")[0]["status"])
            stale = item
            with self.assertRaisesRegex(RuntimeError, "已变化"):
                api.update(stale["uid"], stale["revision"], due_time="16:00")
            fresh = api.list(keyword="交材料", view="archived")["items"][0]
            result = api.update(fresh["uid"], fresh["revision"], done=False, due_date="", due_time="")
            self.assertEqual("pending", result["item"]["status"])
            self.assertEqual("", result["item"]["due_date"])

    def test_changed_retry_payload_is_not_silently_accepted(self):
        remote = FakeGitHub()
        api = service(remote)
        key = str(uuid.uuid4())
        api.add("todo: 联系老师", key)
        with self.assertRaisesRegex(ValueError, "请求标识"):
            api.add("todo: 联系学生", key)
        with self.assertRaisesRegex(ValueError, "请求标识"):
            api.add("todo: 联系老师\n额外事项", key)
        self.assertEqual(1, remote.writes)

    def test_conflict_does_not_overwrite_or_change_local_database(self):
        for flag in ("conflict", "race_before_preflight"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory, patched_todo_storage(directory):
                todo_db.init_db()
                todo_db.add_todo("只在本地")
                before = Path(todo_db.DB_PATH).read_bytes()
                remote = FakeGitHub()
                setattr(remote, flag, True)
                with self.assertRaisesRegex(RuntimeError, "远端数据已更新"):
                    service(remote).add("云端新增", str(uuid.uuid4()))
                self.assertEqual(0, remote.writes)
                self.assertEqual(before, Path(todo_db.DB_PATH).read_bytes())

    def test_corrupt_backup_fails_closed(self):
        remote = FakeGitHub()
        remote.content = "# 待办清单备份\n- 记录数量：5\n被损坏的内容"
        with self.assertRaisesRegex(RuntimeError, "备份格式"):
            service(remote).add("不能覆盖", str(uuid.uuid4()))
        self.assertEqual(0, remote.writes)

    def test_missing_credentials_never_falls_back_to_stale_local_data(self):
        with self.assertRaisesRegex(RuntimeError, "无法读取"):
            TodoChatService(environ={}).list()

    def test_read_pagination_and_deleted_items(self):
        remote = FakeGitHub()
        api = service(remote)
        api.add("第一条\n第二条\n第三条", str(uuid.uuid4()))
        count = remote.writes
        page = api.list(limit=2)
        self.assertEqual(2, len(page["items"]))
        self.assertEqual(3, page["total"])
        self.assertEqual(1, len(api.list(offset=page["next_offset"])["items"]))
        self.assertEqual(count, remote.writes)

    def test_invalid_input_never_writes(self):
        remote = FakeGitHub()
        api = service(remote)
        for text in ("todo:", "# 待办", "a\n## TODO-10\nmalformed", "a" * 8001):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                api.add(text, str(uuid.uuid4()))
        for value in ("2026-02-30", "10/1"):
            with self.assertRaises(ValueError):
                api.add("测试", str(uuid.uuid4()), due_date=value)
        with self.assertRaises(ValueError):
            api.add("测试", str(uuid.uuid4()), due_time="25:99")
        self.assertEqual(0, remote.writes)

    def test_old_id_is_preserved_and_uid_prevents_cross_device_collisions(self):
        records = [{"id": 25, "content": "旧记录", "record_date": "2026-09-01",
                    "created_at": "2026-09-01 10:00:00", "updated_at": "2026-09-01 10:00:00"}]
        with snapshot_db(records) as db:
            original = db.get_todos()[0]
            self.assertEqual(25, original["id"])
            db.add_todo("本机新增")
            incoming = {**db.get_todos()[0], "uid": str(uuid.uuid4()), "content": "另一台电脑新增"}
            db.import_todo_records([incoming])
            self.assertEqual(3, len(db.get_todos()))
            self.assertEqual(3, len({r["uid"] for r in db.get_todos()}))
            db.import_todo_records([incoming])
            self.assertEqual(3, len(db.get_todos()))

    def test_remote_update_does_not_resurrect_local_newer_deletion(self):
        with snapshot_db([]) as db:
            record_id = db.add_todo("事项")
            old = copy.deepcopy(db.get_todos())
            db.delete_todo(record_id)
            db.import_todo_records(old)
            self.assertEqual([], db.get_todos())


if __name__ == "__main__":
    unittest.main()
