import unittest
from bili_recall_compat import format_watch_item, search_records, video_url


class WatchedVideoRecallTests(unittest.TestCase):
    def test_recall_without_embeddings_returns_real_link_and_content(self):
        cache = {"BV1Cz4y147KQ": {"title": "蓝鲸科普", "content_analyzed": True,
                                  "analysis_basis": "video_media", "analysis": "实际抽帧内容"}}
        result = search_records(cache, [], "蓝鲸")
        self.assertEqual(len(result), 1)
        self.assertIn("https://www.bilibili.com/video/BV1Cz4y147KQ", result[0])
        self.assertIn("实际抽帧内容", result[0])

    def test_metadata_preview_is_not_claimed_as_watched(self):
        cache = {"BV1Cz4y147KQ": {"title": "蓝鲸", "content_analyzed": False, "summary": "猜测"}}
        self.assertEqual(search_records(cache, [], "蓝鲸"), [])

    def test_failed_evaluation_keeps_link_without_false_zero_rating(self):
        text = format_watch_item({"bvid": "BV1Cz4y147KQ", "evaluation_status": "failed", "score": 0})
        self.assertIn("评价未生成", text)
        self.assertNotIn("0分", text)
        self.assertIn("BV1Cz4y147KQ", text)

    def test_invalid_identifier_never_becomes_a_link(self):
        self.assertEqual(video_url({"bvid": "../private"}), "")


if __name__ == "__main__":
    unittest.main()
