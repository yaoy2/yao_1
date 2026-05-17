import tempfile
import unittest
from pathlib import Path

import wechat_core


class WechatArchiverRoutesTest(unittest.TestCase):
    def test_classifies_raw_wechat_link_route(self):
        route = wechat_core.classify_archive_request(
            "归档raw\nhttps://mp.weixin.qq.com/s/example"
        )

        self.assertEqual(route["route_id"], "link_raw")
        self.assertEqual(route["archive_type"], "raw")
        self.assertEqual(route["input_kind"], "link")

    def test_classifies_course_local_file_route(self):
        route = wechat_core.classify_archive_request(
            r"归档课题 E:\docs\project.pdf"
        )

        self.assertEqual(route["route_id"], "file_course")
        self.assertEqual(route["archive_type"], "course")
        self.assertEqual(route["input_kind"], "file")

    def test_classifies_academy_local_file_route(self):
        route = wechat_core.classify_archive_request(
            r"归档学院 E:\docs\notice.docx"
        )

        self.assertEqual(route["route_id"], "file_academy")
        self.assertEqual(route["archive_type"], "academy")
        self.assertFalse(route["streamlit_supported"])

    def test_extract_local_paths_handles_quoted_paths(self):
        paths = wechat_core.extract_local_paths(
            r'归档竞赛 "E:\材料\竞赛通知.pdf" E:\材料\报名表.xlsx'
        )

        self.assertEqual(paths, [r"E:\材料\竞赛通知.pdf", r"E:\材料\报名表.xlsx"])

    def test_copy_local_files_preserves_unique_names(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "notice.pdf"
            source.write_text("demo", encoding="utf-8")
            (Path(target_dir) / "notice.pdf").write_text("old", encoding="utf-8")

            original_target = wechat_core.TARGET_DIRS["course"]
            try:
                wechat_core.TARGET_DIRS["course"] = target_dir
                results = wechat_core.archive_local_files([str(source)], "course")
            finally:
                wechat_core.TARGET_DIRS["course"] = original_target

            self.assertTrue(results[0]["ok"])
            self.assertTrue(results[0]["path"].endswith("notice_1.pdf"))
            self.assertEqual(Path(results[0]["path"]).read_text(encoding="utf-8"), "demo")


if __name__ == "__main__":
    unittest.main()
