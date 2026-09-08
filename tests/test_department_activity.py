import base64
import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from utils import department_activity as activity


TODAY = date(2026, 9, 8)


def sample_budget():
    data = activity.set_rosters(activity.new_budget(2026), list(range(1, 10)), [])
    for month, names in {1: ["张三", "李四"], 2: ["张三", "李四", "王五"], 3: ["张三"],
                         9: ["张三", "李四", "王五", "赵六"], 10: ["甲", "乙"]}.items():
        data = activity.set_rosters(data, [month], names)
    return data


class MonthlyCalculationTest(unittest.TestCase):
    def test_nonconsecutive_reimbursement_and_current_month_accrual(self):
        data = activity.set_reimbursed_months(sample_budget(), [3, 1], TODAY)
        result = activity.summarize(data, TODAY)
        self.assertEqual(300, result["total"])
        self.assertEqual(90, result["reimbursed"])
        self.assertEqual(210, result["balance"])
        self.assertEqual([1, 3], result["reimbursed_months"])
        rows = activity.monthly_rows(data, TODAY)
        self.assertEqual("未报销", rows[1]["报销状态"])
        self.assertEqual(90, rows[1]["预算（元）"])
        self.assertEqual("未到月份", rows[9]["报销状态"])
        self.assertEqual(60, rows[9]["预算（元）"])

    def test_month_rollover_accrues_saved_future_roster(self):
        self.assertEqual(300, activity.summarize(sample_budget(), TODAY)["total"])
        self.assertEqual(360, activity.summarize(sample_budget(), date(2026, 10, 1))["total"])

    def test_missing_roster_is_not_zero_or_a_complete_total(self):
        data = activity.set_rosters(activity.new_budget(2026), [1], ["张三"])
        summary = activity.summarize(data, TODAY)
        self.assertEqual(30, summary["known_total"])
        self.assertEqual(list(range(2, 10)), summary["missing_months"])
        for field in ("total", "reimbursed", "balance"):
            self.assertIsNone(summary[field])
        self.assertIsNone(activity.monthly_rows(data, TODAY)[1]["教师人数"])

    def test_confirmed_zero_people_and_no_reimbursements(self):
        data = activity.set_rosters(activity.new_budget(2026), list(range(1, 13)), [])
        data = activity.set_reimbursed_months(data, [], TODAY)
        result = activity.summarize(data, TODAY)
        self.assertEqual((0, 0, 0), (result["total"], result["reimbursed"], result["balance"]))

    def test_past_and_future_years(self):
        data = activity.set_rosters(activity.new_budget(2026), list(range(1, 13)), ["张三"])
        data = activity.set_reimbursed_months(data, [1], TODAY)
        self.assertEqual(360, activity.summarize(data, date(2027, 2, 1))["total"])
        future_year = activity.summarize(data, date(2025, 12, 31))
        self.assertEqual((0, 0, 0), (future_year["total"], future_year["reimbursed"], future_year["balance"]))

    def test_clock_uses_beijing_date_on_utc_month_boundary(self):
        utc_now = datetime(2026, 8, 31, 16, 1, tzinfo=timezone.utc)
        with patch.object(activity, "datetime") as clock:
            clock.now.side_effect = lambda tz: utc_now.astimezone(tz)
            self.assertEqual(date(2026, 9, 1), activity.today_in_shanghai())

    def test_future_and_missing_roster_cannot_be_reimbursed(self):
        for months in ([10], [0], [13]):
            with self.subTest(months=months), self.assertRaises(ValueError):
                activity.set_reimbursed_months(sample_budget(), months, TODAY)
        with self.assertRaises(ValueError):
            activity.set_reimbursed_months(activity.new_budget(2026), [1], TODAY)

    def test_repeated_reimbursement_does_not_double_count_and_can_be_corrected(self):
        data = activity.set_reimbursed_months(sample_budget(), [1, 3, 1], TODAY)
        self.assertEqual(90, activity.summarize(data, TODAY)["reimbursed"])
        data = activity.set_reimbursed_months(data, [1], TODAY)
        self.assertEqual(60, activity.summarize(data, TODAY)["reimbursed"])

    def test_editing_paid_headcount_requires_removing_reimbursement(self):
        data = activity.set_reimbursed_months(sample_budget(), [1], TODAY)
        original = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, "已报销"):
            activity.set_rosters(data, [2, 1], ["甲"])
        self.assertEqual(original, data)
        corrected = activity.set_rosters(data, [1], ["更正姓名", "李四"])
        self.assertEqual(60, activity.summarize(corrected, TODAY)["reimbursed"])
        unpaid = activity.set_reimbursed_months(data, [], TODAY)
        self.assertEqual(["甲"], activity.set_rosters(unpaid, [1], ["甲"])["months"]["1"])

    def test_name_parsing_keeps_same_name_people_and_months_independent(self):
        names = activity.parse_names(" 张三\n李四，王五、赵六；王 斌\t张三\n")
        self.assertEqual(["张三", "李四", "王五", "赵六", "王 斌", "张三"], names)
        data = activity.set_rosters(activity.new_budget(2026), [1, 2], names)
        data["months"]["1"].append("新教师")
        self.assertEqual(6, len(data["months"]["2"]))
        columns = activity.roster_columns(data)
        self.assertEqual(12, len(columns))
        self.assertEqual({7}, {len(column) for column in columns.values()})
        self.assertEqual("待补全", columns["3月"][0])

    def test_invalid_saved_structure_is_rejected(self):
        for field, value in (("year", 2025), ("months", {}), ("reimbursed_months", [1, 1]),
                             ("reimbursement_confirmed", "false")):
            data = sample_budget()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                activity.validate_budget(data, 2026)


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        return self.payload


class RemoteStore:
    def __init__(self, data=None):
        self.data = data
        self.sha = "v1" if data else None
        self.put_status = 200
        self.put_calls = []

    def get(self, *args, **kwargs):
        if self.data is None:
            return Response(404, {})
        return Response(200, {"sha": self.sha,
                              "content": base64.b64encode(json.dumps(self.data).encode()).decode()})

    def put(self, *args, **kwargs):
        payload = kwargs["json"]
        self.put_calls.append(payload)
        if self.put_status == 200:
            self.data = json.loads(base64.b64decode(payload["content"]))
            self.sha = "v2"
        return Response(self.put_status, {"content": {"sha": self.sha}})


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)
        self.patcher = patch.object(activity, "DATA_DIR", self.data_dir)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.path = self.data_dir / "department_activity_budget_2026.json"
        self.cloud = {"secrets": {"github_backup_token": "test-token"}, "environ": {}}
        self.local = {"secrets": {}, "environ": {}}

    def test_new_local_load_does_not_create_data(self):
        loaded = activity.load_budget(2026, **self.local)
        self.assertEqual(activity.new_budget(2026), loaded["data"])
        self.assertFalse(self.path.exists())

    def test_local_save_survives_reload_and_rejects_stale_save(self):
        snapshot = activity.load_budget(2026, **self.local)
        saved = activity.save_budget(sample_budget(), snapshot, **self.local)
        loaded = activity.load_budget(2026, **self.local)
        self.assertEqual(saved["data"], loaded["data"])
        self.assertEqual(saved["version"], loaded["version"])
        before = self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "已更新"):
            activity.save_budget(activity.new_budget(2026), snapshot, **self.local)
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_local_file_is_not_silently_reset(self):
        self.path.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            activity.load_budget(2026, **self.local)
        self.assertEqual("broken", self.path.read_text())

    def test_cloud_is_authoritative_and_local_backup_updates_after_success(self):
        self.path.write_text(json.dumps(activity.new_budget(2026)), encoding="utf-8")
        remote = RemoteStore(sample_budget())
        snapshot = activity.load_budget(2026, session=remote, **self.cloud)
        self.assertEqual(sample_budget(), snapshot["data"])
        data = activity.set_reimbursed_months(snapshot["data"], [1, 3], TODAY)
        saved = activity.save_budget(data, snapshot, session=remote, **self.cloud)
        self.assertEqual(saved["data"], json.loads(self.path.read_bytes()))
        self.assertEqual([1, 3], remote.data["reimbursed_months"])
        self.assertEqual("v1", remote.put_calls[0]["sha"])
        self.assertEqual("v2", saved["version"])

    def test_new_cloud_file_uses_create_without_sha(self):
        remote = RemoteStore()
        snapshot = activity.load_budget(2026, session=remote, **self.cloud)
        activity.save_budget(sample_budget(), snapshot, session=remote, **self.cloud)
        self.assertNotIn("sha", remote.put_calls[0])

    def test_remote_changed_since_read_stops_before_put_or_local_change(self):
        remote = RemoteStore(sample_budget())
        snapshot = activity.load_budget(2026, session=remote, **self.cloud)
        remote.sha = "changed"
        self.path.write_text("local baseline", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "远端数据已更新"):
            activity.save_budget(sample_budget(), snapshot, session=remote, **self.cloud)
        self.assertEqual([], remote.put_calls)
        self.assertEqual("local baseline", self.path.read_text())
        self.assertEqual([], list(self.data_dir.glob("*.tmp")))

    def test_put_conflict_or_failure_does_not_replace_local_backup(self):
        for status in (409, 403, 500):
            remote = RemoteStore(sample_budget())
            snapshot = activity.load_budget(2026, session=remote, **self.cloud)
            remote.put_status = status
            self.path.write_text("local baseline", encoding="utf-8")
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                activity.save_budget(sample_budget(), snapshot, session=remote, **self.cloud)
            self.assertEqual("local baseline", self.path.read_text())

    def test_cloud_read_failure_does_not_fall_back_to_stale_local_data(self):
        self.path.write_text(json.dumps(sample_budget()), encoding="utf-8")
        remote = RemoteStore(sample_budget())
        with patch.object(remote, "get", return_value=Response(500, {})), self.assertRaises(RuntimeError):
            activity.load_budget(2026, session=remote, **self.cloud)

    def test_source_change_requires_refresh_before_saving(self):
        local_snapshot = activity.load_budget(2026, **self.local)
        with self.assertRaisesRegex(RuntimeError, "保存位置已变化"):
            activity.save_budget(sample_budget(), local_snapshot, session=RemoteStore(), **self.cloud)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
