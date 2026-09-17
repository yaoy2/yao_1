"""Chat access to M14; GitHub is the shared ledger, never a second todo store."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from utils import github_backup_sync, todo_db

REPO_PATH = "data/todo_items_backup.md"


def local_secrets():
    path = Path(todo_db.ROOT_DIR) / ".streamlit" / "secrets.toml"
    return tomllib.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


class GitHubCliSession:
    """Reuse gh's login locally without extracting or persisting its credentials."""

    def __init__(self, executable):
        self.executable = executable

    def _request(self, method, url, params=None, json_body=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise ValueError("GitHub CLI 仅允许访问 GitHub API。")
        endpoint = parsed.path.lstrip("/")
        if params:
            endpoint += "?" + urlencode(params)
        command = [self.executable, "api", "--hostname", "github.com", "--include", "--method", method, endpoint]
        if json_body is not None:
            command += ["--input", "-"]
        result = subprocess.run(command, input=json.dumps(json_body) if json_body is not None else None,
                                text=True, encoding="utf-8", capture_output=True, timeout=45,
                                env={**os.environ, "GH_PROMPT_DISABLED": "1"})
        output = result.stdout.replace("\r\n", "\n")
        header, _, body = output.partition("\n\n")
        status = re.match(r"HTTP/\S+\s+(\d{3})", header)
        if not status:
            raise RuntimeError("无法通过本机 GitHub CLI 读取服务，请检查 gh 登录和网络；保存结果尚未确认。")
        response = type("GitHubCliResponse", (), {})()
        response.status_code = int(status[1])
        response.json = lambda: json.loads(body)
        return response

    def get(self, url, *, params=None, **kwargs):
        return self._request("GET", url, params=params)

    def put(self, url, *, json, **kwargs):
        return self._request("PUT", url, json_body=json)


def local_service():
    secrets = local_secrets()
    if github_backup_sync.get_backup_sync_config(secrets)["enabled"]:
        return TodoChatService(secrets=secrets)
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("请配置 GITHUB_BACKUP_TOKEN，或先登录本机 GitHub CLI。")
    # The custom transport ignores Authorization headers and uses gh's own login.
    return TodoChatService(secrets=secrets, session=GitHubCliSession(executable),
                           environ={**os.environ, "GITHUB_BACKUP_TOKEN": "handled-by-gh-cli"})


@contextmanager
def snapshot_db(records):
    # A separate module instance avoids changing the Streamlit module's global paths.
    spec = importlib.util.spec_from_file_location("m14_snapshot", todo_db.__file__)
    db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(db)
    with tempfile.TemporaryDirectory(prefix="m14-") as directory:
        db.DB_PATH = str(Path(directory) / "todos.db")
        db.BACKUP_MD_PATH = str(Path(directory) / "backup.md")
        db.init_db()
        db.import_todo_records(records)
        yield db


def revision(record):
    data = {key: value for key, value in record.items() if key not in {"id", "revision"}}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def public_record(record):
    return {**record, "revision": revision(record)}


def validate_due(value, kind):
    if value is None or value == "":
        return
    if kind == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("截止日期请使用 YYYY-MM-DD。")
        date.fromisoformat(value)
    elif not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("截止时间请使用 HH:MM。")


class TodoChatService:
    def __init__(self, secrets=None, environ=None, session=None):
        self.secrets = secrets
        self.environ = os.environ if environ is None else environ
        self.session = session

    def _read(self):
        result = github_backup_sync.read_file_from_github(
            REPO_PATH, secrets=self.secrets, environ=self.environ, session=self.session)
        if not result.get("ok"):
            raise RuntimeError("无法读取 M14 远端备份；请检查 GitHub 连接，未写入待办。")
        text = result["content"]
        records = todo_db.parse_markdown_backup(text)
        count = re.search(r"^- 记录数量：(\d+)\s*$", text, re.M)
        if not result.get("sha") or not count or int(count[1]) != len(records):
            raise RuntimeError("M14 备份格式或版本无效，已停止写入，避免丢失记录。")
        ids = [item["id"] for item in records]
        uids = [todo_db.record_uid(item) for item in records]
        if len(set(ids)) != len(ids) or len(set(uids)) != len(uids) or any(i <= 0 for i in ids):
            raise RuntimeError("M14 备份存在重复或无效标识，已停止写入。")
        return records, result["sha"]

    def _write(self, db, sha):
        result = github_backup_sync.sync_file_to_github(
            db.BACKUP_MD_PATH, REPO_PATH, "data: update M14 from chat",
            secrets=self.secrets, environ=self.environ, session=self.session, expected_sha=sha)
        if not result.get("ok"):
            raise RuntimeError("待办没有同步成功，请检查连接后重试。")
        return result

    def list(self, keyword="", view="active", offset=0, limit=50):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("分页范围无效。")
        records, _ = self._read()
        with snapshot_db(records) as db:
            matches = db.get_todos(keyword=keyword, view=view)
            matches = [r for r in matches if r["status"] != "deleted"]
            return {"items": [public_record(r) for r in matches[offset:offset + limit]],
                    "total": len(matches), "next_offset": offset + limit if offset + limit < len(matches) else None}

    def add(self, content, request_id, due_date=None, due_time=None):
        """A stable request UUID makes retries safe even after an ambiguous network result."""
        request_uuid = uuid.UUID(request_id)
        content = str(content).strip()
        content = re.sub(r"^(?:提醒我\s*[:：]?|待办\s*[:：]?|todo\b\s*[:：]?)\s*", "", content, flags=re.I)
        if not content or len(content) > 8000 or re.search(r"^## TODO-|^### 内容\s*$", content, re.M):
            raise ValueError("请输入有效待办内容（最多 8000 字），不能包含备份控制标题。")
        validate_due(due_date, "date")
        validate_due(due_time, "time")
        records, sha = self._read()
        with snapshot_db(records) as db:
            items = db.split_todo_text(content)
            if not items or len(items) > 50:
                raise ValueError("每次请添加 1 至 50 条待办。")
            existing = {r["uid"]: r for r in db.get_todos(view="all")}
            previous_batch = [existing[str(uuid.uuid5(request_uuid, str(index)))]
                              for index in range(50) if str(uuid.uuid5(request_uuid, str(index))) in existing]
            if previous_batch and len(previous_batch) != len(items):
                raise ValueError("请求标识已用于另一批待办；请核对后使用新的 request_id。")
            created, results = 0, []
            for index, text in enumerate(items):
                uid = str(uuid.uuid5(request_uuid, str(index)))
                if uid in existing:
                    # The same operation key must not silently refer to a different request.
                    previous = existing[uid]
                    if previous["content"] != text or (due_date is not None and previous["due_date"] != due_date) or (due_time is not None and previous["due_time"] != due_time):
                        raise ValueError("请求标识已用于另一条内容；请核对后使用新的 request_id。")
                    results.append(previous)
                    continue
                record_id = db.add_todo(text, due_date=due_date, due_time=due_time, uid=uid)
                results.append(next(r for r in db.get_todos(view="all") if r["id"] == record_id))
                created += 1
            if created:
                self._write(db, sha)
            return {"ok": True, "created": created, "items": [public_record(r) for r in results],
                    "notifications": False}

    def update(self, uid, expected_revision, due_date=None, due_time=None, done=None):
        validate_due(due_date, "date")
        validate_due(due_time, "time")
        if due_date is None and due_time is None and done is None:
            raise ValueError("请提供截止日期、截止时间或完成状态。")
        records, sha = self._read()
        with snapshot_db(records) as db:
            record = next((r for r in db.get_todos(view="all") if r["uid"] == uid and r["status"] != "deleted"), None)
            if record is None:
                raise ValueError("没有找到该待办，请先查询清单。")
            if revision(record) != expected_revision:
                raise RuntimeError("该待办已变化，请重新查询并核对后再修改。")
            db.update_todo(record["id"], due_date=due_date, due_time=due_time)
            if done is True:
                db.complete_todo(record["id"])
            elif done is False:
                db.reopen_todo(record["id"])
            self._write(db, sha)
            updated = next(r for r in db.get_todos(view="all") if r["uid"] == uid)
            return {"ok": True, "item": public_record(updated), "notifications": False}
