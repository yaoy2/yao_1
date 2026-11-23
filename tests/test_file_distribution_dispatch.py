import hashlib
import json
from pathlib import Path

from integrations.file_distribution import dingtalk_dispatch as ding, engine
from tests.test_file_distribution_invoices import write_invoice


def _write(root, name, number=17, suffix=""):
    return write_invoice(root, name, f"成都东软学院健康医疗科技学院文件\n"
                         f"成东软健康院发〔2026〕{number}号 签发人：测试\n"
                         f"关于召开业务会议的通知\n各系、部：\n合成测试内容{suffix}\n"
                         "健康医疗科技学院 2026 年 11 月 20 日印发")


def test_real_pdf_archives_only_after_confirmation_and_retries_sync(tmp_path, monkeypatch):
    source = _write(tmp_path, "健康院发【2026】17号-示例.pdf")
    untouched = write_invoice(tmp_path, "校发[2026]1号-学校通知.pdf", "校发〔2026〕1号")

    def offline():
        raise ding.DingTalkError("未登录")

    monkeypatch.setattr(engine.DingTalkRegister, "connect", offline)
    plan = engine.scan(tmp_path, "dispatch")
    item, = plan.items
    assert source.exists() and not Path(item.destination).exists()
    assert (item.document_number, item.document_title, item.document_date) == (
        "成东软健康院发〔2026〕17号", "关于召开业务会议的通知", "2026-11-20")
    result = engine.execute(plan, [source.name])
    result_item, = result.items
    assert result_item.status == "moved" and result_item.ding_status == "pending"
    assert untouched.exists() and not source.exists()
    assert hashlib.sha256(Path(item.destination).read_bytes()).hexdigest() == item.sha256

    class Register:
        def register(self, selected, archived):
            assert archived == Path(item.destination)
            assert selected.document_number == item.document_number
            return "已确认"

    monkeypatch.setattr(engine.DingTalkRegister, "connect", Register)
    retry, = engine.retry_dispatch_sync(tmp_path).items
    assert retry.ding_status == "synced"
    assert not engine.retry_dispatch_sync(tmp_path).items


def test_dispatch_duplicate_and_conflicting_version_use_canonical_number(tmp_path):
    first = _write(tmp_path, "成东软健康院发〔2026〕17号-测试.pdf")
    second = _write(tmp_path, "健康院发[2026]17号-另一版.pdf", suffix="不同")
    bad = _write(tmp_path, "健康院发[2026]19号-文号不一致.pdf", number=18)
    rows = {item.name: item for item in engine.scan(tmp_path, "dispatch").items}
    assert rows[first.name].status == rows[second.name].status == "collision"
    assert rows[bad.name].status == "review"


def test_ding_register_creates_one_row_and_verifies_it_on_retry(tmp_path, monkeypatch):
    pdf = tmp_path / "测试.pdf"
    pdf.write_bytes(b"test PDF")
    item = engine.PlanItem(pdf.name, str(pdf), period="2026", size=8,
                           sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                           document_number="成东软健康院发〔2026〕17号", document_title="关于测试的通知",
                           document_date="2026-11-20")
    fields = {ding.NUMBER_FIELD: "num", ding.TITLE_FIELD: "title", ding.DATE_FIELD: "date", ding.ATTACHMENT_FIELD: "pdf"}
    rows, creates = [], []

    def call(exe, app, group, action, *args):
        if (group, action) == ("record", "query"):
            return {"records": rows}
        if (group, action) == ("attachment", "upload"):
            return {"uploadUrl": "https://test.aliyuncs.com/test", "fileToken": "test-token"}
        assert (group, action) == ("record", "create")
        record, = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        creates.append(record)
        rows.append({"recordId": "record1", **record})
        return {}

    monkeypatch.setattr(ding, "_call", call)
    monkeypatch.setattr(ding, "_put", lambda url, content: None)
    register = ding.DingTalkRegister(Path("test-dws"), "base", "table", fields)
    assert "回读确认" in register.register(item, pdf)
    assert "已有" in register.register(item, pdf)
    assert len(creates) == 1
    assert creates[0]["cells"] == {"num": "成东软健康院发[2026]17号", "title": "关于测试的通知",
                                      "date": "2026-11-20", "pdf": [{"fileToken": "test-token"}]}
