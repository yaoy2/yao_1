import unittest

from app.classifier import classify_item


class ClassifierTest(unittest.TestCase):
    def test_movie_with_year_and_version(self):
        result = classify_item("流浪地球2.2023.1080p.BluRay.mkv")
        self.assertEqual("电影", result.category)
        self.assertEqual("2023", result.year)
        self.assertIn("流浪地球2", result.suggested_name)
        self.assertIn("medium", result.confidence)

    def test_tv_season_episode(self):
        result = classify_item("三体.2023.S01E01.2160p.WEB-DL.mkv")
        self.assertEqual("电视剧", result.category)
        self.assertEqual("01", result.season)
        self.assertEqual("01", result.episode)
        self.assertEqual("high", result.confidence)
        self.assertIn("Season 01", result.suggested_path)

    def test_tv_chinese_episode_only_is_low_confidence(self):
        result = classify_item("某剧第02集.mp4")
        self.assertIn(result.category, {"待识别", "电视剧"})
        if result.category == "电视剧":
            self.assertEqual("low", result.confidence)

    def test_anime_fansub_and_episode(self):
        result = classify_item("[Nekomoe kissaten] 葬送的芙莉莲 [01][1080p].mkv")
        self.assertEqual("动漫", result.category)
        self.assertEqual("01", result.episode)

    def test_documentary(self):
        result = classify_item("舌尖上的中国.纪录片.2012.mkv", full_path="/云下载/纪录片/舌尖上的中国.纪录片.2012.mkv")
        self.assertEqual("纪录片", result.category)

    def test_variety(self):
        result = classify_item("奔跑吧.2024.第10期.mkv")
        self.assertEqual("综艺", result.category)

    def test_music_video(self):
        result = classify_item("周杰伦.嘉年华演唱会.2024.mkv")
        self.assertEqual("音乐视频", result.category)

    def test_subtitle_archive_image(self):
        self.assertEqual("字幕", classify_item("movie.chs.srt").category)
        self.assertEqual("压缩包", classify_item("files.part1.rar").category)
        self.assertEqual("图片", classify_item("poster.png").category)

    def test_unknown_video_is_pending(self):
        result = classify_item("random_clip.mp4")
        self.assertEqual("待识别", result.category)
        self.assertEqual("low", result.confidence)

    def test_generic_video(self):
        result = classify_item("会议录屏_2024.mp4")
        self.assertEqual("普通视频", result.category)

    def test_directory_is_other(self):
        result = classify_item("电影", is_directory=True)
        self.assertEqual("其他", result.category)


if __name__ == "__main__":
    unittest.main()
