import unittest

from app.classifier import classify_item
from app.series import cluster_series, series_key, time_bucket


class TestSeriesKey(unittest.TestCase):
    def test_same_series_names_share_key(self):
        a = series_key("某课程 第01集.mp4")
        b = series_key("某课程 第02集.mp4")
        self.assertTrue(a)
        self.assertEqual(a, b)

    def test_episode_tags_removed(self):
        self.assertEqual(
            series_key("[字幕组]番剧名 [01].mkv"),
            series_key("[字幕组]番剧名 [02].mkv"),
        )

    def test_sxxexx_removed(self):
        self.assertEqual(
            series_key("Show Name S01E01 1080p.mp4"),
            series_key("show name s02e05 720p.mkv"),
        )

    def test_trailing_numbers_removed(self):
        self.assertEqual(
            series_key("my series - 03.mp4"),
            series_key("my series - 12.mp4"),
        )

    def test_mixed_word_numbers_kept(self):
        # one2048 是字母数字混合词，"e204" 不应被当成集数误删；
        # 分隔的 0323/0324 会被去掉，嵌在词里的 jul172/jul173 保留（不误合并）。
        key1 = series_key("one2048.com-0323-jul172-FHDncfk.mp4")
        key2 = series_key("one2048.com-0324-jul173-FHDncfk.mp4")
        self.assertIn("one2048", key1)
        self.assertIn("one2048", key2)
        self.assertNotEqual(key1, key2)

    def test_short_or_numeric_key_is_empty(self):
        self.assertEqual(series_key("123.mp4"), "")


class TestClusterSeries(unittest.TestCase):
    def _row(self, idx, name, path="/星标视频/a"):
        return {
            "id": idx,
            "name": name,
            "full_path": f"{path}/{name}",
            "extension": "." + name.rsplit(".", 1)[-1].lower(),
        }

    def test_two_files_form_series(self):
        groups = cluster_series(
            [
                self._row(1, "系列A 第1集.mp4"),
                self._row(2, "系列A 第2集.mp4"),
                self._row(3, "完全不同的电影 2019.mkv"),
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].file_row_ids, [1, 2])
        self.assertTrue(groups[0].same_parent)

    def test_non_video_ignored(self):
        groups = cluster_series(
            [
                self._row(1, "系列A 第1集.jpg"),
                self._row(2, "系列A 第2集.jpg"),
            ]
        )
        self.assertEqual(groups, [])

    def test_cross_directory_series(self):
        groups = cluster_series(
            [
                self._row(1, "番剧名 [01].mkv", path="/星标视频/x"),
                self._row(2, "番剧名 [02].mkv", path="/星标视频/y"),
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0].same_parent)


class TestTimeBucket(unittest.TestCase):
    def test_month_bucket(self):
        self.assertEqual(time_bucket("2026-08-15 10:00:00"), "2026-08")
        self.assertEqual(time_bucket("2026-08-15T10:00:00Z"), "2026-08")

    def test_invalid(self):
        self.assertEqual(time_bucket(None), "")
        self.assertEqual(time_bucket(""), "")
        self.assertEqual(time_bucket("unknown"), "")


class TestMoviePath(unittest.TestCase):
    def test_movie_grouped_by_title(self):
        c = classify_item("流浪地球 2019 1080p.mp4", "/星标视频/x", False, ".mp4")
        self.assertEqual(c.category, "电影")
        self.assertEqual(c.suggested_path, "/电影/流浪地球 (2019)/流浪地球 (2019) 1080p.mp4")


if __name__ == "__main__":
    unittest.main()


class TestImageSeriesMatching(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from app.config import load_settings
        from app.db import connect, init_db

        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        env_path = root / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "OPENLIST_BASE_URL=http://127.0.0.1:5244",
                    "OPENLIST_USERNAME=organizer-readonly",
                    "OPENLIST_PASSWORD=secret",
                    "ALLOWED_ROOT=/星标视频",
                    "DEFAULT_SCAN_DIR=/星标视频",
                    f"DB_PATH={root / '115_index.sqlite'}",
                    f"LOG_PATH={root / 'organizer.log'}",
                    "WRITE_MODE=false",
                ]
            ),
            encoding="utf-8",
        )
        self.settings = load_settings(env_path)
        from app.db import connect as _c, init_db as _i

        _i(self.settings.db_path)
        self.conn = _c(self.settings.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _insert(self, name, ext, path):
        from app.db import upsert_file

        return upsert_file(
            self.conn,
            {
                "file_id": "fid-" + name,
                "file_id_source": "native",
                "name": name,
                "full_path": f"{path}/{name}",
                "parent_id": "p1",
                "is_directory": False,
                "size": 100,
                "extension": ext,
                "sha1": "",
                "created_at": "1700000000",
                "updated_at": "1700000000",
            },
        )

    def test_images_follow_matching_series(self):
        from app.planner import rebuild_plans

        self._insert("旅行日记 第1集.mp4", ".mp4", "/星标视频/a")
        self._insert("旅行日记 第2集.mp4", ".mp4", "/星标视频/a")
        self._insert("旅行日记 第1集.jpg", ".jpg", "/星标视频/a")
        self._insert("无关照片.jpg", ".jpg", "/星标视频/a")
        self.conn.commit()
        rebuild_plans(self.settings)
        rows = {
            r["original_name"]: r
            for r in self.conn.execute(
                "SELECT original_name, category, suggested_path FROM organize_plans"
            )
        }
        self.assertEqual(
            rows["旅行日记 第1集.jpg"]["suggested_path"],
            "/系列/旅行日记/旅行日记 第1集.jpg",
        )
        self.assertEqual(
            rows["无关照片.jpg"]["suggested_path"], "/图片/无关照片.jpg"
        )


if __name__ == "__main__":
    unittest.main()
