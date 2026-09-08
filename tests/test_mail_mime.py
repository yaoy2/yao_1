import hashlib
import unittest
from email import policy
from email.header import Header
from email.message import EmailMessage
from email.parser import BytesParser

from utils.mail_mime import parse_message


class MailMimeTest(unittest.TestCase):
    def parse(self, message, **kwargs):
        raw = message if isinstance(message, bytes) else message.as_bytes(policy=policy.SMTP)
        return parse_message(raw, received_at=kwargs.get("received_at", "2026-09-08T10:00:00+08:00"),
                             folder="INBOX", source_url="https://mail.nsu.edu.cn/owa/")

    def mail(self):
        message = EmailMessage()
        message["Message-ID"] = "<mime-fixture@example.test>"
        message["From"] = "教务处 <office@example.test>"
        message["To"] = "测试用户 <recipient@example.test>"
        message["Subject"] = "教学安排通知"
        message["Date"] = "Mon, 7 Sep 2026 09:00:00 +0800"
        message.set_content("请查看教学安排。", charset="utf-8")
        return message

    def test_utf8_headers_body_and_internaldate(self):
        message = self.mail()
        message["Received"] = "internal host details"
        message["X-Session-Token"] = "fixture-private-token"
        parsed = self.parse(message)
        self.assertEqual("<mime-fixture@example.test>", parsed["id"])
        self.assertEqual("2026-09-08T10:00:00+08:00", parsed["received_at"])
        self.assertEqual("教务处 <office@example.test>", parsed["sender"])
        self.assertEqual("教学安排通知", parsed["subject"])
        self.assertEqual("请查看教学安排。", parsed["body_text"])
        self.assertEqual(parsed["body_text"], parsed["summary"])
        self.assertEqual("INBOX", parsed["folder"])
        self.assertEqual("待整理", parsed["category"])
        self.assertEqual("https://mail.nsu.edu.cn/owa/", parsed["source_url"])
        self.assertIn("Subject: 教学安排通知", parsed["headers_text"])
        self.assertNotIn("fixture-private-token", parsed["headers_text"])
        self.assertNotIn("internal host details", parsed["headers_text"])
        self.assertFalse(parsed["authentication_notice"])

    def test_gbk_body_rfc2047_subject_and_filename(self):
        subject = Header("学院材料汇总", "gbk").encode()
        filename = Header("汇总表.xlsx", "gbk").encode()
        raw = (f"Subject: {subject}\r\nMIME-Version: 1.0\r\n"
               "Content-Type: multipart/mixed; boundary=fixture\r\n\r\n"
               "--fixture\r\nContent-Type: text/plain; charset=gbk\r\n\r\n").encode("ascii")
        raw += "中文材料，请提交。".encode("gbk")
        raw += (f"\r\n--fixture\r\nContent-Type: application/octet-stream\r\n"
                f'Content-Disposition: attachment; filename="{filename}"\r\n'
                "Content-Transfer-Encoding: base64\r\n\r\nYWJj\r\n--fixture--\r\n").encode("ascii")
        parsed = self.parse(raw)
        self.assertEqual("学院材料汇总", parsed["subject"])
        self.assertEqual("中文材料，请提交。", parsed["body_text"])
        self.assertEqual("汇总表.xlsx", parsed["attachments"][0]["name"])
        self.assertEqual(b"abc", parsed["attachments"][0]["data"])

    def test_rfc2231_continued_filename_and_path_sanitization(self):
        raw = (b"MIME-Version: 1.0\r\nContent-Type: application/pdf\r\n"
               b"Content-Disposition: attachment;\r\n"
               b" filename*0*=utf-8''..%2F%E6%9D%90%E6%96%99;\r\n"
               b" filename*1*=%E9%80%9A%E7%9F%A5.pdf\r\n\r\nfixture pdf")
        attachment = self.parse(raw)["attachments"][0]
        self.assertEqual("材料通知.pdf", attachment["name"])
        self.assertEqual("application/pdf", attachment["content_type"])

    def test_duplicate_and_inline_attachments_have_distinct_stable_ids(self):
        message = self.mail()
        for payload in (b"first", b"second", b"first"):
            message.add_attachment(payload, maintype="application", subtype="pdf", filename="同名.pdf")
        message.add_attachment(b"inline image", maintype="image", subtype="png",
                               filename="图.png", disposition="inline", cid="<image>")
        raw = message.as_bytes()
        parsed = self.parse(raw)
        attachments = parsed["attachments"]
        self.assertEqual(["同名.pdf"] * 3 + ["图.png"], [a["name"] for a in attachments])
        self.assertEqual(4, len({a["id"] for a in attachments}))
        self.assertTrue(parsed["attachments_complete"])
        self.assertEqual(4, parsed["expected_attachment_count"])
        self.assertEqual(attachments, self.parse(raw)["attachments"])
        for attachment in attachments:
            self.assertEqual(len(attachment["data"]), attachment["size"])
            self.assertEqual(hashlib.sha256(attachment["data"]).hexdigest(), attachment["sha256"])

    def test_unnamed_non_body_parts_are_attachments(self):
        message = self.mail()
        message.make_mixed()
        for mime in ("image/png", "application/pdf", "text/calendar"):
            part = EmailMessage()
            maintype, subtype = mime.split("/")
            part.set_content(b"part data", maintype=maintype, subtype=subtype)
            message.attach(part)
        parsed = self.parse(message)
        self.assertEqual(3, len(parsed["attachments"]))
        self.assertEqual([".png", ".pdf", ".ics"], [a["name"][-4:] for a in parsed["attachments"]])
        self.assertEqual("请查看教学安排。", parsed["body_text"])

    def test_empty_attachment_is_listed_but_never_reported_complete(self):
        message = self.mail()
        message.add_attachment(b"valid fixture", maintype="application", subtype="pdf", filename="通知.pdf")
        message.add_attachment(b"", maintype="application", subtype="octet-stream", filename="空表.xlsx")
        parsed = self.parse(message)
        self.assertFalse(parsed["attachments_complete"])
        self.assertEqual(2, parsed["expected_attachment_count"])
        populated, empty = parsed["attachments"]
        self.assertEqual(b"valid fixture", populated["data"])
        self.assertNotIn("error", populated)
        self.assertEqual("空表.xlsx", empty["name"])
        self.assertEqual(b"", empty["data"])
        self.assertEqual(0, empty["size"])
        self.assertEqual(hashlib.sha256(b"").hexdigest(), empty["sha256"])
        self.assertEqual("missing", empty["status"])
        self.assertEqual("MIME_ATTACHMENT_EMPTY", empty["error"])

    def test_empty_body_without_attachments_is_complete(self):
        message = self.mail()
        message.set_content("")
        parsed = self.parse(message)
        self.assertEqual("", parsed["body_text"])
        self.assertEqual([], parsed["attachments"])
        self.assertTrue(parsed["attachments_complete"])
        self.assertEqual(0, parsed["expected_attachment_count"])

    def test_truncated_multipart_retains_readable_content_without_claiming_complete(self):
        message = self.mail()
        message.add_attachment(b"valid fixture", maintype="application", subtype="pdf", filename="通知.pdf")
        message.set_boundary("fixture-close-boundary")
        complete = message.as_bytes(policy=policy.SMTP)
        raw = complete.removesuffix(b"--fixture-close-boundary--\r\n")
        self.assertNotEqual(complete, raw)
        parsed = self.parse(raw)
        self.assertFalse(parsed["attachments_complete"])
        self.assertEqual("请查看教学安排。", parsed["body_text"])
        self.assertEqual(1, parsed["expected_attachment_count"])
        self.assertEqual(b"valid fixture", parsed["attachments"][0]["data"])

    def test_broken_nested_multipart_is_not_hidden_by_valid_outer_boundary(self):
        raw = (b"Content-Type: multipart/mixed; boundary=outer-fixture\r\n\r\n"
               b"--outer-fixture\r\nContent-Type: multipart/alternative; boundary=inner-fixture\r\n\r\n"
               b"--inner-fixture\r\nContent-Type: text/plain\r\n\r\nVisible fixture body\r\n"
               b"--outer-fixture--\r\n")
        parsed = self.parse(raw)
        self.assertEqual("Visible fixture body", parsed["body_text"])
        self.assertFalse(parsed["attachments_complete"])

    def test_missing_boundary_definition_or_start_is_incomplete_without_fake_files(self):
        for content_type in (b"multipart/mixed", b"multipart/mixed; boundary=missing-fixture"):
            with self.subTest(content_type=content_type):
                raw = b"Content-Type: " + content_type + b"\r\n\r\nUnstructured fixture payload"
                parsed = self.parse(raw)
                self.assertFalse(parsed["attachments_complete"])
                self.assertEqual([], parsed["attachments"])

    def test_unrelated_header_defect_does_not_reject_readable_body(self):
        raw = (b" orphaned header continuation\r\nSubject: Fixture notice\r\n"
               b"Content-Type: text/plain; charset=utf-8\r\n\r\nReadable body")
        mime = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertIn("FirstHeaderLineIsContinuationDefect", [type(defect).__name__ for defect in mime.defects])
        parsed = self.parse(raw)
        self.assertEqual("Readable body", parsed["body_text"])
        self.assertTrue(parsed["attachments_complete"])

    def test_plain_body_preferred_over_html_alternative(self):
        message = self.mail()
        message.add_alternative("<p>另一版本HTML正文</p>", subtype="html")
        parsed = self.parse(message)
        self.assertEqual("请查看教学安排。", parsed["body_text"])
        self.assertEqual([], parsed["attachments"])

    def test_html_only_uses_visible_text_without_resources_or_hidden_content(self):
        message = self.mail()
        message.set_content('''<html><head><title>元数据</title><style>secret-css</style></head>
          <body><p>学院 &amp; 教学</p><p>请查看<strong>安排</strong>。</p>
          <script>secret-script</script><div hidden>hidden-one</div>
          <div style="display: none">hidden-two</div><span aria-hidden="true">hidden-three</span>
          <input type="hidden" value="hidden-four"><img src="https://remote.test/pixel" alt="tracking">
          <a href="https://remote.test/?token=fixture">打开通知</a>
          <span style="opacity: 0.5">半透明文本可见</span></body></html>''', subtype="html")
        parsed = self.parse(message)
        self.assertIn("学院 & 教学", parsed["body_text"])
        self.assertIn("请查看安排。", parsed["body_text"])
        self.assertIn("打开通知", parsed["body_text"])
        self.assertIn("半透明文本可见", parsed["body_text"])
        for hidden in ("元数据", "secret", "hidden", "remote.test", "tracking", "fixture"):
            self.assertNotIn(hidden, parsed["body_text"])

    def test_empty_plain_body_falls_back_to_html(self):
        message = self.mail()
        message.set_content("")
        message.add_alternative("<p>可见内容</p>", subtype="html")
        self.assertEqual("可见内容", self.parse(message)["body_text"])

    def test_message_attachment_stays_eml_and_does_not_pollute_body(self):
        outer = self.mail()
        inner = EmailMessage()
        inner["Subject"] = "嵌套邮件"
        inner.set_content("仅在附件里的正文")
        outer.add_attachment(inner)
        parsed = self.parse(outer)
        self.assertEqual("请查看教学安排。", parsed["body_text"])
        self.assertEqual(1, len(parsed["attachments"]))
        attachment = parsed["attachments"][0]
        self.assertTrue(attachment["name"].endswith(".eml"))
        nested = BytesParser(policy=policy.default).parsebytes(attachment["data"])
        self.assertEqual("嵌套邮件", str(nested["Subject"]))
        self.assertIn("仅在附件里的正文", nested.get_content())

    def test_missing_message_id_uses_raw_sha256(self):
        message = self.mail()
        del message["Message-ID"]
        raw = message.as_bytes()
        first = self.parse(raw)
        second = self.parse(raw)
        expected = hashlib.sha256(raw).hexdigest()
        self.assertEqual("sha256:" + expected, first["id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(expected, first["raw_sha256"])
        self.assertEqual("", first["internet_message_id"])
        self.assertNotEqual(first["id"], self.parse(raw + b"\r\n")["id"])

    def test_authentication_notices_do_not_return_codes_or_reset_links(self):
        fixtures = [("您的验证码 483921", "请使用 483921 登录。"),
                    ("Account notification", "Your one-time password is 483921."),
                    ("Reset your password", "https://account.test/reset?token=fixture-private"),
                    ("密码重置通知", "重置链接包含 fixture-private")]
        for subject, body in fixtures:
            with self.subTest(subject=subject):
                message = self.mail()
                message.replace_header("Subject", subject)
                message.set_content(body)
                message.add_attachment(b"fixture-private", maintype="application", subtype="octet-stream",
                                       filename="sensitive.bin")
                parsed = self.parse(message)
                self.assertTrue(parsed["authentication_notice"])
                self.assertEqual("", parsed["body_text"])
                self.assertEqual("", parsed["headers_text"])
                self.assertEqual([], parsed["attachments"])
                self.assertNotIn("483921", repr(parsed))
                self.assertNotIn("fixture-private", repr(parsed))

    def test_unknown_charset_and_undeclared_gbk_are_recovered(self):
        for charset in (b"x-nonexistent-fixture", b"us-ascii"):
            raw = b"Content-Type: text/plain; charset=" + charset + b"\r\n\r\n" + "中文正文".encode("gbk")
            self.assertEqual("中文正文", self.parse(raw)["body_text"])

    def test_authentication_detection_checks_html_alternative(self):
        message = self.mail()
        message.add_alternative("<p>Your verification code is 483921.</p>", subtype="html")
        parsed = self.parse(message)
        self.assertTrue(parsed["authentication_notice"])
        self.assertEqual("", parsed["body_text"])
        self.assertNotIn("483921", repr(parsed))

    def test_bad_attachment_transfer_data_is_not_reported_as_complete(self):
        for encoding, payload in ((b"base64", b"a"), (b"base64", b"YWJj!!!"),
                                  (b"x-unknown-transfer", b"fixture")):
            raw = (b"Content-Type: application/octet-stream\r\n"
                   b"Content-Disposition: attachment; filename=data.bin\r\n"
                   b"Content-Transfer-Encoding: " + encoding + b"\r\n\r\n" + payload)
            with self.subTest(encoding=encoding, payload=payload):
                with self.assertRaisesRegex(ValueError, "attachment content transfer"):
                    self.parse(raw)

    def test_received_time_fallback_requires_timezone(self):
        message = self.mail()
        self.assertEqual("2026-09-07T09:00:00+08:00", self.parse(message, received_at="")["received_at"])
        message.replace_header("Date", "Mon, 7 Sep 2026 09:00:00 -0000")
        self.assertEqual("", self.parse(message, received_at="")["received_at"])

    def test_summary_is_a_short_excerpt_and_does_not_invent_actions(self):
        message = self.mail()
        message.set_content("请查看教学安排。" * 100)
        parsed = self.parse(message)
        self.assertEqual(201, len(parsed["summary"]))
        self.assertTrue(parsed["body_text"].startswith(parsed["summary"][:-1]))
        self.assertNotIn("actions", parsed)
        self.assertNotIn("due_at", parsed)


if __name__ == "__main__":
    unittest.main()
