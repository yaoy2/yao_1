import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

import wechat_core


class WechatArchiverRoutesTest(unittest.TestCase):
    def test_linked_image_is_preserved_with_its_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            builder = wechat_core.MarkdownBuilder("article", Path(directory))
            builder.download_image = Mock(return_value="![配图](assets/article/img_001.jpg)")
            link = BeautifulSoup('<a href="https://example.com">说明<img data-src="https://example.com/pic.jpg" alt="配图"></a>', "html.parser").a
            builder.walk(link)
            self.assertEqual(builder.to_markdown(), "[说明![配图](assets/article/img_001.jpg)](https://example.com)")
            builder.download_image.assert_called_once_with("https://example.com/pic.jpg", alt="配图")

    def test_same_title_articles_keep_independent_image_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = Mock()
            page.content.return_value = '<div id="js_content"><img src="https://example.com/pic.jpg"></div>'
            meta = {"title": "同名文章", "published": "2026-09-30", "source": "https://example.com"}
            responses = [Mock(content=content, headers={"Content-Type": "image/jpeg"})
                         for content in (b"first-image", b"second-image")]
            with patch.dict(wechat_core.TARGET_DIRS, {"course": str(root)}), \
                 patch.object(wechat_core, "extract_meta", return_value=meta), \
                 patch.object(wechat_core, "save_log"), \
                 patch.object(wechat_core.requests, "get", side_effect=responses):
                first = wechat_core.archive_one(page, "https://example.com/1", "course")
                second = wechat_core.archive_one(page, "https://example.com/2", "course")
            self.assertTrue(first["ok"], first["message"])
            self.assertTrue(second["ok"], second["message"])
            first_path, second_path = Path(first["path"]), Path(second["path"])
            self.assertNotEqual(first_path, second_path)
            for path, content in ((first_path, b"first-image"), (second_path, b"second-image")):
                self.assertEqual((root / "assets" / path.stem / "img_001.jpg").read_bytes(), content)
                self.assertIn(f"assets/{path.stem}/img_001.jpg", path.read_text(encoding="utf-8"))

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
