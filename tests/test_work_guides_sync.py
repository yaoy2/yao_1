import base64
from copy import deepcopy
import hashlib
import json
from unittest.mock import Mock

import pytest

from utils import work_guides as guides
from utils import work_guides_sync as cloud
from tests.test_work_guides import example


CONFIG = {"github_backup": {"token": "test-only", "repo": cloud.PRIVATE_REPO, "branch": "main"}}


class Remote:
    def __init__(self, document=None):
        self.document = deepcopy(document)
        self.sha = self.digest(document) if document else None
        self.writes = []
        self.private = True
        self.put_status = None
        self.bad_readback = False

    @staticmethod
    def digest(document):
        return hashlib.sha1(guides.serialize(document).encode()).hexdigest()

    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        if "/contents/" not in url:
            return Mock(status_code=200, json=lambda: {"private": self.private, "full_name": cloud.PRIVATE_REPO})
        assert url.endswith(guides.REPO_PATH)
        if self.document is None:
            return Mock(status_code=404)
        return Mock(status_code=200, json=lambda: {"encoding": "base64", "sha": "b" * 40 if self.bad_readback and self.writes else self.sha,
                                                  "content": base64.b64encode(guides.serialize(self.document).encode()).decode()})

    def put(self, url, json, **kwargs):
        self.writes.append(deepcopy(json))
        if self.put_status:
            return Mock(status_code=self.put_status)
        assert json.get("sha") == self.sha
        self.document = __import__("json").loads(base64.b64decode(json["content"]))
        self.sha = self.digest(self.document)
        return Mock(status_code=200, json=lambda: {"content": {"sha": self.sha}})


def test_absent_file_is_empty_only_after_verifying_the_private_repository():
    remote = Remote()
    result = cloud.load_document(CONFIG, {}, remote)
    assert result["ok"] and not result["document"]["guides"] and result["sha"] is None
    remote.private = False
    assert not cloud.load_document(CONFIG, {}, remote)["ok"]


@pytest.mark.parametrize("config", [{"github_backup": {"token": "test", "repo": "yaoy2/yao_1"}},
                                   {"github_backup": {"token": "test", "repo": cloud.PRIVATE_REPO, "branch": "other"}}, {}])
def test_wrong_public_or_missing_connection_never_uses_a_transport(config):
    transport = Mock()
    assert not cloud.load_document(config, {}, transport)["ok"]
    transport.get.assert_not_called()


def test_create_and_edit_are_read_back_and_verified():
    remote = Remote()
    document, gid = guides.update_guide(guides.empty_document(), {"title": "年度工作"})
    result = cloud.save_document(document, None, CONFIG, {}, remote)
    assert result["ok"] and result["document"] == document
    changed, _ = guides.update_guide(document, {"contacts": "确认后的对接人"}, gid)
    result = cloud.save_document(changed, result["sha"], CONFIG, {}, remote)
    assert result["ok"] and remote.document == changed and len(remote.writes) == 2
    assert not cloud.save_document(changed, None, CONFIG, {}, remote)["ok"]
    assert len(remote.writes) == 2


def test_version_conflict_and_409_never_report_success():
    document, gid, _, _ = example()
    remote = Remote(document)
    changed, _ = guides.update_guide(document, {"summary": "本机改动"}, gid)
    result = cloud.save_document(changed, "f" * 40, CONFIG, {}, remote)
    assert result["conflict"] and not remote.writes
    remote.put_status = 409
    result = cloud.save_document(changed, remote.sha, CONFIG, {}, remote)
    assert result["conflict"] and remote.document == document


def test_failed_readback_and_secret_transport_errors_are_not_exposed():
    remote = Remote()
    document, _ = guides.update_guide(guides.empty_document(), {"title": "工作"})
    remote.bad_readback = True
    result = cloud.save_document(document, None, CONFIG, {}, remote)
    assert not result["ok"] and "尚未确认" in result["message"]
    transport = Mock()
    transport.get.side_effect = RuntimeError("private-token-marker")
    result = cloud.load_document(CONFIG, {}, transport)
    assert not result["ok"] and "private-token-marker" not in json.dumps(result)


def test_invalid_cloud_payload_and_removal_cannot_be_written():
    document, _, _, _ = example()
    remote = Remote(document)
    transport = Mock()
    transport.get.side_effect = [remote.get("repo", allow_redirects=False), Mock(status_code=200, json=lambda: {"encoding": "base64", "sha": "a" * 40, "content": "bad!"})]
    assert not cloud.load_document(CONFIG, {}, transport)["ok"]
    removed = deepcopy(document)
    removed["revision"] += 1
    removed["guides"] = []
    assert not cloud.save_document(removed, remote.sha, CONFIG, {}, remote)["ok"]
    assert not remote.writes
