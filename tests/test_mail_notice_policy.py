import unittest
from unittest.mock import patch

from utils.mail_notice_policy import EdgeOnlineOnlyError, is_edge_source, is_minutes_name, is_sent_folder


class NoticePolicyTests(unittest.TestCase):
    def test_only_edge_online_evidence_is_eligible(self):
        self.assertTrue(is_edge_source("edge", "https://mail.nsu.edu.cn/owa/#path=/mail/sentitems"))
        for transport, url in (("imap", "https://mail.nsu.edu.cn/owa/"),
                               ("edge", "https://example.com/owa/"),
                               ("edge", "http://mail.nsu.edu.cn/owa/"),
                               ("edge", "https://user:secret@mail.nsu.edu.cn/owa/"),
                               ("edge", "https://mail.nsu.edu.cn/owa/?token=secret"),
                               ("edge", "file:///downloaded-mail.eml")):
            with self.subTest(transport=transport, url=url):
                self.assertFalse(is_edge_source(transport, url))

    def test_legacy_collection_is_blocked_before_setup_credentials_or_network(self):
        from scripts import mail_imap_collect
        with patch.object(mail_imap_collect, "load_setup_config", side_effect=AssertionError("no config read")), \
             patch.object(mail_imap_collect, "read_credential", side_effect=AssertionError("no credentials")), \
             patch.object(mail_imap_collect.mail_imap, "connect", side_effect=AssertionError("no IMAP")):
            with self.assertRaises(EdgeOnlineOnlyError):
                mail_imap_collect.collect_workspace("never-open-this-path")

    def test_source_fallback_is_blocked_before_reading_old_files_or_imap(self):
        from utils import mail_filing_source
        with patch.object(mail_filing_source, "_local_source", side_effect=AssertionError("no local mail")), \
             patch.object(mail_filing_source, "_imap_source", side_effect=AssertionError("no IMAP")):
            result = mail_filing_source.read_source("never-open-this-path", {"id": "test"})
        self.assertEqual(["EDGE_ONLINE_ONLY"], result["error_codes"])
        self.assertIsNone(result["raw"])

    def test_legacy_setup_never_opens_login_window_or_network(self):
        from scripts import mail_imap_setup
        with patch.object(mail_imap_setup.imaplib, "IMAP4_SSL", side_effect=AssertionError("no IMAP login")):
            with self.assertRaises(EdgeOnlineOnlyError):
                mail_imap_setup.verify_connection({}, "not-a-real-password")
            with self.assertRaises(EdgeOnlineOnlyError):
                mail_imap_setup.run_window({})

    def test_only_sent_mail_is_eligible(self):
        for name in ("已发送", "已发送邮件", "Sent", "Sent Items", "Sent Messages"):
            with self.subTest(name=name):
                self.assertTrue(is_sent_folder(name))
        for name in ("INBOX", "收件箱", "Outbox", "发件箱", "Drafts", "工作存档", "制度文件", "", None):
            with self.subTest(name=name):
                self.assertFalse(is_sent_folder(name))
        self.assertTrue(is_sent_folder("发送归档", ["\\Sent"]))
        self.assertTrue(is_sent_folder("发送归档", "(\\HasNoChildren \\Sent)"))
        self.assertFalse(is_sent_folder("INBOX", ["\\Sent"]))
        self.assertFalse(is_sent_folder("Outbox", ["\\Sent"]))

    def test_minutes_are_blocked_before_content_is_available(self):
        for name in ("Fw: 学院会议纪要", "党政联席会纪要.pdf", "例会紀要.docx",
                     "培训纪要", "关于报送会议纪要的通知", "会\u200b议纪要.docx",
                     "会议记录.xlsx", "Meeting Minutes.pdf", "meeting_minutes.docx",
                     "MINUTES.txt", "２０２６-会议 纪要.pdf"):
            with self.subTest(name=name):
                self.assertTrue(is_minutes_name(name))
        for name in ("退休返聘审批表.docx", "新进教职工第二阶段培训计划.xlsx",
                     "提交月报通知", "学院院报.xlsx", "通知.pdf"):
            with self.subTest(name=name):
                self.assertFalse(is_minutes_name(name))


if __name__ == "__main__":
    unittest.main()
