import builtins
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from utils import mail_review_text as review


def zipped(name, content):
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return stream.getvalue()


def attachment(name, data):
    return {"id": "test-attachment", "name": name, "data": data}


class MailReviewTextTests(unittest.TestCase):
    def extract(self, name, data):
        return review.extract_attachment_reviews([attachment(name, data)])[0]

    def test_docx_and_plain_are_read_in_memory_without_file_open(self):
        raw = zipped("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>9月20日前报送</w:t></w:r></w:p></w:body></w:document>'.encode())
        with patch.object(builtins, "open", side_effect=AssertionError("file IO forbidden")):
            docx = self.extract("通知.docx", raw)
            csv = self.extract("通知.csv", "责任人,截止日期\n学院,9月20日".encode("gb18030"))
        self.assertEqual(("read", "9月20日前报送", False), (docx["status"], docx["text"], docx["truncated"]))
        self.assertEqual("read", csv["status"])
        self.assertIn("责任人", csv["text"])

    def test_unsupported_empty_and_large_sources_are_not_claimed_read(self):
        for name, data, reason in [("资料.zip", zipped("a.txt", "body"), "暂不支持此附件格式"),
                                   ("资料.rar", b"RAR", "暂不支持此附件格式"),
                                   ("资料.txt", b"", "附件为空或未取得内容"),
                                   ("资料.txt", b"x" * (review.MAX_ATTACHMENT_BYTES + 1), "附件超过15MiB读取上限")]:
            with self.subTest(name=name, reason=reason):
                result = self.extract(name, data)
                self.assertEqual(("unavailable", "", reason), (result["status"], result["text"], result["reason"]))

    def test_archive_suffix_cannot_be_reclassified_as_plain_text_by_mime(self):
        stream = BytesIO()
        with zipfile.ZipFile(stream, "w"):
            pass
        for name, data in [("附件.ZIP", stream.getvalue()), ("附件.rar", b"Rar!\x1a\x07\x00"),
                           ("附件.7z", b"plain-looking archive header")]:
            with self.subTest(name=name):
                value = {**attachment(name, data), "content_type": "text/plain"}
                result = review.extract_attachment_reviews([value])[0]
                self.assertEqual(("unavailable", "", False),
                                 (result["status"], result["text"], result["truncated"]))
                self.assertEqual("暂不支持此附件格式", result["reason"])

    def test_zip_expansion_and_xml_entities_are_rejected_before_parsing(self):
        oversized = zipped("word/document.xml", b"x" * (review.MAX_PART_BYTES + 1))
        self.assertEqual("附件解压内容超过读取上限", self.extract("通知.docx", oversized)["reason"])
        stream = BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for number in range(3):
                archive.writestr(str(number), b"x" * (7 * 1024 * 1024))
        self.assertEqual("附件解压内容超过读取上限", self.extract("通知.xlsx", stream.getvalue())["reason"])
        entity = zipped("word/document.xml", b'<!DOCTYPE doc [<!ENTITY secret "private">]><doc>&secret;</doc>')
        result = self.extract("通知.docx", entity)
        self.assertEqual("unavailable", result["status"])
        self.assertNotIn("private", result["reason"])

    def test_text_and_pdf_limits_are_explicit_and_scanned_pdf_is_unavailable(self):
        exact = self.extract("通知.txt", ("长" * review.MAX_TEXT).encode())
        self.assertEqual(("read", False), (exact["status"], exact["truncated"]))
        result = self.extract("通知.txt", ("长" * (review.MAX_TEXT + 1)).encode())
        self.assertEqual(("partial", True, review.MAX_TEXT), (result["status"], result["truncated"], len(result["text"])))
        page = SimpleNamespace(extract_text=Mock(return_value="一页文字"))
        reader = SimpleNamespace(is_encrypted=False, pages=[page] * 61)
        module = SimpleNamespace(PdfReader=Mock(return_value=reader))
        with patch.object(review.importlib, "import_module", return_value=module):
            result = self.extract("通知.pdf", b"mock PDF")
        self.assertEqual(("partial", True), (result["status"], result["truncated"]))
        self.assertEqual(60, page.extract_text.call_count)
        page.extract_text.return_value = ""
        reader.pages = [page]
        with patch.object(review.importlib, "import_module", return_value=module):
            result = self.extract("扫描.pdf", b"mock PDF")
        self.assertEqual("unavailable", result["status"])

    def test_missing_component_and_raw_errors_do_not_leak_content(self):
        with patch.object(review.importlib, "import_module", side_effect=ImportError("private-error-marker")):
            result = self.extract("通知.pdf", b"mock PDF")
        self.assertEqual("本机缺少PDF解析组件", result["reason"])
        with patch.object(review, "_docx", side_effect=RuntimeError("private-error-marker")):
            result = self.extract("通知.docx", b"bad document")
        self.assertEqual("unavailable", result["status"])
        self.assertNotIn("private-error-marker", result["reason"])

    def test_xlsx_uses_memory_readonly_values_and_enforces_row_column_limits(self):
        sheet = SimpleNamespace(title="Sheet", max_row=301, max_column=41,
                                iter_rows=Mock(return_value=iter([("学院", "9月20日")])) )
        workbook = SimpleNamespace(worksheets=[sheet], close=Mock())
        module = SimpleNamespace(load_workbook=Mock(return_value=workbook))
        with patch.object(review.importlib, "import_module", return_value=module):
            result = self.extract("通知.xlsx", zipped("fake.xml", b"unused"))
        self.assertEqual(("partial", True), (result["status"], result["truncated"]))
        self.assertIn("学院", result["text"])
        sheet.iter_rows.assert_called_once_with(max_row=300, max_col=40, values_only=True)
        self.assertIsInstance(module.load_workbook.call_args.args[0], BytesIO)
        self.assertEqual({"read_only": True, "data_only": True, "keep_links": False}, module.load_workbook.call_args.kwargs)
        workbook.close.assert_called_once()

    def test_xlsx_missing_dimensions_cannot_claim_bounded_read_is_complete(self):
        for dimensions in [(None, None), (None, 1), (1, None)]:
            with self.subTest(dimensions=dimensions):
                sheet = SimpleNamespace(title="Sheet", max_row=dimensions[0], max_column=dimensions[1],
                                        iter_rows=Mock(return_value=iter([("可读内容",)])))
                workbook = SimpleNamespace(worksheets=[sheet], close=Mock())
                module = SimpleNamespace(load_workbook=Mock(return_value=workbook))
                with patch.object(review.importlib, "import_module", return_value=module):
                    result = self.extract("通知.xlsx", zipped("fake.xml", b"unused"))
                self.assertEqual(("partial", True), (result["status"], result["truncated"]))
                self.assertIn("可读内容", result["text"])
                self.assertIn("无法确认完整性", result["reason"])
                workbook.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
