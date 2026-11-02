"""Invoice classification and actual moves use synthetic, isolated documents only."""

import hashlib
from pathlib import Path
from unittest.mock import Mock
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from openpyxl import Workbook

from integrations.file_distribution import engine, invoices


INVOICE_TEXT = """电子发票（普通发票）
发票号码：26000000000000000001
开票日期：2026年11月02日
购买方名称：合成测试单位甲
销售方名称：合成测试单位乙
统一社会信用代码/纳税人识别号：91000000000000000X
项目名称：测试用品
金额：100.00 税额：1.00
价税合计（大写）：壹佰零壹元整 （小写）：￥101.00
"""


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "Ding2026"
    (path / "07_年度工作档案/2026年/财务/2026年发票").mkdir(parents=True)
    return path


def write_invoice(root, name="dzfp_26000000000000000001_测试.pdf", text=INVOICE_TEXT):
    path = root / name
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    document = canvas.Canvas(str(path))
    document.setFont("STSong-Light", 12)
    for index, line in enumerate(text.splitlines()):
        document.drawString(40, 780 - index * 24, line)
    document.save()
    return path


@pytest.mark.parametrize("mode", ["invoice", ("monthly", "invoice"), ("minutes", "attendance", "invoice")])
def test_explicit_invoice_selection_moves_original_bytes(root, mode):
    source = write_invoice(root)
    original = source.read_bytes()
    plan = engine.scan(root, mode)
    assert source.read_bytes() == original  # Preview does not move or change the source.
    assert not (root / "98_系统").exists()
    assert len(plan.items) == 1
    item = plan.items[0]
    assert (item.status, item.kind, item.period) == ("ready", "发票", "2026")
    assert Path(item.destination).parent == root / "07_年度工作档案/2026年/财务/2026年发票"
    result = engine.execute(plan, [source.name])
    assert result.moved == 1
    assert not source.exists()
    assert Path(item.destination).read_bytes() == original


@pytest.mark.parametrize('mode', ['monthly', 'weekly', ('minutes',), ('attendance',)])
def test_unselected_invoices_are_never_read_or_included(root, monkeypatch, mode):
    source = write_invoice(root)
    classifier = Mock(side_effect=AssertionError('Unselected invoice must not be read'))
    monkeypatch.setattr(engine, 'classify_invoice', classifier)
    assert not engine.scan(root, mode).items
    classifier.assert_not_called()
    assert source.exists()


def test_name_alone_and_request_screenshot_are_not_enough(root, monkeypatch):
    image = root / "竞赛九队伍发票.JPG"
    image.write_bytes(b"synthetic-image-placeholder")
    reader = Mock(return_value=("学校名称 汇款人 汇款金额 发票金额 是否需要发票 发票类型 发票抬头 增值税普通发票 10800", ""))
    monkeypatch.setattr(invoices, "read_image_text", reader)
    assert invoices.classify_invoice(image, root).status == "review"
    reader.assert_called_once_with(image)


def test_picture_is_accepted_only_after_local_ocr_evidence(root, monkeypatch):
    image = root / "DZFP_图片.PNG"
    image.write_bytes(b"synthetic-image-placeholder")
    monkeypatch.setattr(invoices, "read_image_text", Mock(return_value=(INVOICE_TEXT, "")))
    assert invoices.classify_invoice(image, root).status == "ready"


@pytest.mark.parametrize("name", ["发票申请.pdf", "发票统计.xlsx", "合同发票条款分析.xlsx", "发票查验.pdf"])
def test_supporting_documents_never_become_invoices_from_the_name(root, monkeypatch, name):
    source = root / name
    source.write_bytes(b"supporting document")
    read = Mock(side_effect=AssertionError("supporting document should not require OCR"))
    monkeypatch.setattr(invoices, "read_invoice_text", read)
    assert invoices.classify_invoice(source, root).status == "skip"
    read.assert_not_called()


@pytest.mark.parametrize("text", ["发票申请说明\n发票号码 开票日期 购买方 价税合计", INVOICE_TEXT.replace("价税合计", "费用")])
def test_incomplete_invoice_evidence_is_not_moved(root, text):
    source = write_invoice(root, name="发票待核对.pdf", text=text)
    plan = engine.scan(root, "invoice")
    assert plan.items[0].status == "review"
    assert source.exists()


def test_missing_year_or_conflicting_years_do_not_guess_destination(root):
    for text in (INVOICE_TEXT.replace("2026年11月02日", "日期模糊"), INVOICE_TEXT + "另一开票日期：2025年01月01日"):
        source = write_invoice(root, text=text)
        assert invoices.classify_invoice(source, root).status == "review"


def test_missing_annual_folder_is_not_created(root):
    source = write_invoice(root, text=INVOICE_TEXT.replace("2026年11月02日", "2025年11月02日"))
    decision = invoices.classify_invoice(source, root)
    assert decision.status == "review"
    assert "未找到现有的2025年发票文件夹" in decision.reason
    assert not (root / "07_年度工作档案/2025年").exists()


def test_duplicate_under_another_name_is_preserved(root):
    source = write_invoice(root)
    target = root / "07_年度工作档案/2026年/财务/2026年发票/已保存发票.pdf"
    target.write_bytes(source.read_bytes())
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    item = engine.scan(root, "invoice").items[0]
    assert item.status == "duplicate"
    assert source.exists()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


def test_changed_source_is_rejected_at_move_time(root):
    source = write_invoice(root)
    plan = engine.scan(root, "invoice")
    source.write_bytes(source.read_bytes() + b"changed after preview")
    result = engine.execute(plan, [source.name])
    assert result.moved == 0
    assert result.items[0].status == "changed"
    assert source.exists()


def test_ofd_text_is_read_without_extracting_files(root):
    source = root / "发票.ofd"
    with ZipFile(source, "w") as archive:
        archive.writestr("Doc_0/Pages/Page_0/Content.xml",
                         '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016">'
                         f'<ofd:TextCode>{escape(INVOICE_TEXT)}</ofd:TextCode></ofd:Page>')
    assert invoices.classify_invoice(source, root).status == "ready"
    assert not (root / "Doc_0").exists()


def test_compressed_package_and_unreadable_scans_stay_for_review(root, monkeypatch):
    archive = root / "QQ邮箱发票.zip"
    archive.write_bytes(b"not interpreted as a single invoice")
    assert invoices.classify_invoice(archive, root).status == "review"
    source = write_invoice(root)
    monkeypatch.setattr(invoices, "read_document_text", Mock(return_value=("", "扫描PDF未提取到文字")))
    assert invoices.classify_invoice(source, root).status == "review"


def test_invoice_target_does_not_allow_arbitrary_finance_directories(root):
    from integrations.file_distribution.models import Decision
    decision = Decision("ready", kind="发票", relative_dir="07_年度工作档案/2026年/财务/其他资料")
    with pytest.raises(ValueError):
        engine._target(root, decision, "发票.pdf")


def test_verified_zip_keeps_invoice_index_and_moves_original_archive(root, tmp_path):
    source_pdf = write_invoice(tmp_path)
    index = tmp_path / "发票统计.xlsx"
    workbook = Workbook()
    workbook.active.append(["发票号码", "开票日期", "金额"])
    workbook.active.append(["26000000000000000001", "2026-11-02", 101])
    workbook.save(index)
    workbook.close()
    source = root / "QQ邮箱发票.zip"
    with ZipFile(source, "w") as archive:
        archive.write(source_pdf, "票据/001.pdf")
        archive.write(index, "配套清单.xlsx")
    original = source.read_bytes()
    plan = engine.scan(root, "invoice")
    assert (plan.items[0].status, plan.items[0].kind) == ("ready", "发票压缩包")
    result = engine.execute(plan, [source.name])
    assert result.moved == 1
    assert Path(plan.items[0].destination).read_bytes() == original
    assert not (root / "票据").exists()


@pytest.mark.parametrize("extra", ["unrelated.txt", "unrelated.xlsx", "nested.zip"])
def test_zip_with_unrelated_materials_is_not_moved(root, tmp_path, extra):
    invoice = write_invoice(tmp_path)
    archive_path = root / "发票汇总.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(invoice, "001.pdf")
        archive.writestr(extra, b"not a verified invoice index")
    assert invoices.classify_invoice(archive_path, root).status == "review"


def test_mixed_years_and_excessive_archive_members_stay_for_review(root, tmp_path):
    first = write_invoice(tmp_path, "发票2026.pdf")
    second = write_invoice(tmp_path, "发票2025.pdf", INVOICE_TEXT.replace("2026年11月02日", "2025年11月02日"))
    archive_path = root / "发票.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(first, "2026.pdf")
        archive.write(second, "2025.pdf")
    assert invoices.classify_invoice(archive_path, root).status == "review"
    with ZipFile(archive_path, "w") as archive:
        for index in range(51):
            archive.writestr(f"{index}.pdf", b"too many entries")
    assert invoices.classify_invoice(archive_path, root).status == "review"
