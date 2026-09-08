import copy
import unittest

from utils import mail_filing_state as filing
from utils.mail_action_status import ACTIVE_STATUSES, ALL_STATUSES, ARCHIVED_STATUSES, STATUS_LABELS


AT = "2026-09-08T12:00:00+08:00"


def receipt(**changes):
    value = {"request_id": "a" * 32, "requested_at": AT, "updated_at": AT, "status": "pending",
             "destination": "", "saved_count": 0, "total_count": 0, "error_count": 0, "error_codes": []}
    value.update(changes)
    return value


def snapshot():
    return {"messages": [{"id": "m1", "subject": "Mixed children"},
                         {"id": "m2", "triage_status": "archived"},
                         {"id": "m3", "triage_status": "pending"}],
            "actions": [{"id": "a1", "message_id": "m1", "status": "archived"},
                        {"id": "a2", "message_id": "m1", "status": "pending"}]}


class FilingStateTests(unittest.TestCase):
    def test_archived_is_not_an_active_or_completed_work_state(self):
        self.assertEqual("存档", STATUS_LABELS["archived"])
        self.assertIn("archived", ALL_STATUSES)
        self.assertIn("archived", ARCHIVED_STATUSES)
        self.assertNotIn("archived", ACTIVE_STATUSES)

    def test_request_is_any_archived_child_or_unactioned_mail_triage(self):
        data = snapshot()
        self.assertTrue(filing.is_filing_requested(data, "m1"))
        self.assertTrue(filing.is_filing_requested(data, "m2"))
        self.assertFalse(filing.is_filing_requested(data, "m3"))
        self.assertFalse(filing.is_filing_requested(data, "missing"))
        data["messages"][0]["triage_status"] = "archived"
        data["actions"][0]["status"] = "pending"
        self.assertFalse(filing.is_filing_requested(data, "m1"))

    def test_queue_changes_only_eligible_message_receipts_once_per_message(self):
        data = snapshot()
        before = copy.deepcopy(data)
        self.assertEqual(["m1", "m2"], filing.queue_filing(data, ["m1", "m1", "m2", "m3", "missing"], AT))
        for message in data["messages"][:2]:
            self.assertEqual("pending", message["filing"]["status"])
            filing.validate_filing(message["filing"])
            message.pop("filing")
        self.assertEqual(before, data)

    def test_same_second_retry_gets_new_id_and_strictly_newer_request_time(self):
        data = snapshot()
        filing.queue_filing(data, ["m1"], AT)
        first = copy.deepcopy(data["messages"][0]["filing"])
        filing.queue_filing(data, ["m1"], AT)
        second = data["messages"][0]["filing"]
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertGreater(filing._moment(second["requested_at"]), filing._moment(first["requested_at"]))

    def test_cancel_waits_until_no_child_still_requests_and_preserves_success(self):
        data = snapshot()
        filing.queue_filing(data, ["m1", "m2"], AT)
        self.assertEqual([], filing.cancel_unrequested(data, ["m1"], AT))
        data["actions"][0]["status"] = "pending"
        self.assertEqual(["m1"], filing.cancel_unrequested(data, ["m1"], AT))
        cancelled = data["messages"][0]["filing"]
        self.assertEqual("cancelled", cancelled["status"])
        self.assertGreater(filing._moment(cancelled["updated_at"]), filing._moment(cancelled["requested_at"]))
        data["messages"][1].update(triage_status="pending", filing=receipt(status="success"))
        before = copy.deepcopy(data["messages"][1])
        self.assertEqual([], filing.cancel_unrequested(data, ["m2"], AT))
        self.assertEqual(before, data["messages"][1])

    def test_partial_and_error_can_cancel_without_discarding_saved_receipt(self):
        for status in ("partial", "error"):
            with self.subTest(status=status):
                data = snapshot()
                data["messages"][2]["filing"] = receipt(status=status, destination="邮件存档/日期+主题",
                    saved_count=1, total_count=2, error_count=1, error_codes=["ATTACHMENT_EMPTY"])
                self.assertEqual(["m3"], filing.cancel_unrequested(data, ["m3"], AT))
                result = data["messages"][2]["filing"]
                self.assertEqual(("cancelled", 1, "邮件存档/日期+主题"),
                                 (result["status"], result["saved_count"], result["destination"]))

    def test_relative_destination_rejects_drive_escape_and_reserved_names(self):
        self.assertEqual("", filing.safe_relative_destination(""))
        self.assertEqual("邮件存档/2026-09-08_工作通知", filing.safe_relative_destination("邮件存档/2026-09-08_工作通知"))
        for path in ("E:/GoogleDrive/Ding2026", "/邮件存档/a", "邮件存档", "other/a", "邮件存档/../secret",
                     "邮件存档/a/../../secret", "邮件存档\\x", "邮件存档//x", "邮件存档/CON", "邮件存档/name.",
                     "邮件存档/name ", "邮件存档/x:y", "邮件存档/a\nname"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                filing.safe_relative_destination(path)

    def test_public_receipt_drops_local_details_but_validates_safe_fields(self):
        local = receipt(local_path="E:/private/file", body_text="private bytes", attachments=[b"secret"])
        self.assertEqual(receipt(), filing.public_filing(local))
        self.assertIn("local_path", local)
        with self.assertRaises(ValueError):
            filing.validate_filing(local)

    def test_invalid_receipts_are_rejected(self):
        for change in ({"request_id": "not-a-uuid"}, {"requested_at": "2026-09-08"},
                       {"updated_at": "2026-09-07T12:00:00+08:00"}, {"status": "done"},
                       {"saved_count": True}, {"total_count": -1}, {"saved_count": 1},
                       {"error_codes": ["raw private error"]}, {"error_codes": ["ATTACHMENT_EMPTY"] * 2},
                       {"destination": "../outside"}, {"status": "success", "error_count": 1},
                       {"status": "success", "saved_count": 1, "total_count": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                filing.validate_filing(receipt(**change))

    def test_complete_empty_mail_can_have_success_without_a_created_directory(self):
        value = receipt(status="success")
        self.assertIs(value, filing.validate_filing(value))

    def test_new_request_wins_over_late_result_of_old_request(self):
        old = receipt(status="success", updated_at="2026-09-10T12:00:00+08:00")
        new = receipt(request_id="b" * 32, requested_at="2026-09-09T12:00:00+08:00", updated_at="2026-09-09T12:00:00+08:00")
        self.assertEqual(new, filing.merge_filing(old, new))
        self.assertEqual(new, filing.merge_filing(new, old))

    def test_cancelled_request_cannot_be_resurrected_by_late_worker_result(self):
        cancelled = receipt(status="cancelled", updated_at="2026-09-08T12:00:01+08:00")
        late_success = receipt(status="success", updated_at="2026-09-08T12:00:10+08:00")
        self.assertEqual(cancelled, filing.merge_filing(late_success, cancelled))
        self.assertEqual(cancelled, filing.merge_filing(cancelled, late_success))

    def test_same_request_uses_newest_result_and_remote_wins_exact_ties(self):
        local = receipt(status="partial", error_count=1, error_codes=["ATTACHMENT_EMPTY"])
        remote = receipt(status="error", error_count=1, error_codes=["SOURCE_MISSING"])
        self.assertEqual(remote, filing.merge_filing(local, remote))
        newer = receipt(status="success", updated_at="2026-09-08T12:01:00+08:00")
        self.assertEqual(newer, filing.merge_filing(newer, remote))
        self.assertEqual(newer, filing.merge_filing(None, newer))
        self.assertIsNone(filing.merge_filing(None, None))


if __name__ == "__main__":
    unittest.main()
