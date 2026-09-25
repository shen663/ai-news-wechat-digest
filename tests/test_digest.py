import json
import io
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import ai_digest as digest


class DigestTests(unittest.TestCase):
    def test_serverchan_request_contains_digest(self):
        with patch.dict(os.environ, {"SERVERCHAN_SENDKEY": "SCT_test"}), \
             patch.object(digest.urllib.request, "urlopen", return_value=io.BytesIO(b'{"code":0}')) as post:
            digest.send_serverchan("今日 AI", "五条摘要")
        request = post.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("SCT_test.send", request.full_url)
        form = digest.urllib.parse.parse_qs(request.data.decode("utf-8"))
        self.assertEqual(form["title"], ["今日 AI"])
        self.assertEqual(form["desp"], ["五条摘要"])

    def test_deepseek_region_overrides_source_hint(self):
        now = datetime.now(digest.CHINA_TIME)
        articles = [digest.Article(title, f"https://example.com/{i}", now, region, f"source-{i}")
                    for i, (title, region) in enumerate([
                        ("联合国发布人工智能报告", "cn"), ("百度发布新模型", "cn"),
                        ("阿里推出新智能体", "cn"), ("OpenAI releases model", "global"),
                        ("Google updates Gemini", "global"),
                    ])]
        stories = [digest.Story(article, {article.source}, {article.url}, 50 - i)
                   for i, article in enumerate(articles)]
        chosen = [{"id": f"C{i}", "region": "cn" if i in (1, 2) else "global",
                   "title_zh": f"标题{i}", "summary_zh": f"摘要{i}"} for i in range(5)]
        response = {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps({"items": chosen}, ensure_ascii=False)}]}]}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), \
             patch.object(digest.urllib.request, "urlopen",
                          return_value=io.BytesIO(json.dumps(response).encode("utf-8"))) as post:
            items = digest.deepseek_digest(stories, now)
        self.assertEqual(items[0]["region"], "global")
        self.assertIn("【全球】", digest.render_digest(items, now, ai_used=True)[1])
        request = post.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/responses")
        self.assertEqual(json.loads(request.data)["model"], "deepseek-flash")

    def test_deepseek_accepts_one_domestic_story_when_both_regions_are_covered(self):
        now = datetime.now(digest.CHINA_TIME)
        articles = [digest.Article(f"AI event {i}", f"https://example.com/{i}", now,
                                   "cn" if i < 2 else "global", f"source-{i}")
                    for i in range(5)]
        stories = [digest.Story(article, {article.source}, {article.url}, 50 - i)
                   for i, article in enumerate(articles)]
        chosen = [{"id": f"C{i}", "region": "cn" if i == 0 else "global",
                   "title_zh": f"标题{i}", "summary_zh": f"摘要{i}"} for i in range(5)]
        response = {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps({"items": chosen}, ensure_ascii=False)}]}]}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), patch.object(
            digest.urllib.request, "urlopen",
            return_value=io.BytesIO(json.dumps(response).encode("utf-8"))
        ):
            items = digest.deepseek_digest(stories, now)
        self.assertEqual([item["region"] for item in items].count("cn"), 1)

    def test_rss_and_atom_parse_dates_links_and_regions(self):
        rss = b"""<rss><channel><item><title>OpenAI launches a model</title>
        <link>https://example.com/story</link><pubDate>Wed, 23 Sep 2026 10:00:00 GMT</pubDate>
        <description>&lt;p&gt;Details here&lt;/p&gt;</description></item></channel></rss>"""
        source = {"name": "Chinese source", "region": "cn"}
        article = digest.parse_feed(rss, source)[0]
        self.assertEqual(article.region, "global")
        self.assertEqual(article.snippet, "Details here")

        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>DeepSeek releases model</title><link href="https://example.com/deepseek"/>
        <updated>2026-09-23T12:00:00+08:00</updated></entry></feed>"""
        article = digest.parse_feed(atom, {"name": "Global source", "region": "global"})[0]
        self.assertEqual(article.region, "cn")
        self.assertEqual(article.url, "https://example.com/deepseek")
        bing = "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fexample.com%2Fnews%3Fid%3D1&tid=x"
        self.assertEqual(digest.unwrap_news_url(bing), "https://example.com/news?id=1")

    def test_groups_duplicate_reports_and_balances_regions(self):
        now = datetime.now(digest.CHINA_TIME)
        titles = ["DeepSeek releases model", "DeepSeek releases model!", "百度发布新模型",
                  "OpenAI releases new API", "Google announces Gemini update", "Anthropic ships Claude"]
        articles = [digest.Article(title, f"https://example.com/{i}", now - timedelta(hours=i),
                                   "cn" if i < 3 else "global", f"source-{i}")
                    for i, title in enumerate(titles)]
        stories = digest.group_stories(articles, now)
        self.assertEqual(len(stories), 5)
        selected = digest.choose_balanced(stories)
        self.assertEqual(len(selected), 5)
        self.assertGreaterEqual(sum(s.article.region == "cn" for s in selected), 2)
        self.assertGreaterEqual(sum(s.article.region == "global" for s in selected), 2)

    def test_delivery_is_recorded_once(self):
        now = datetime.now(digest.CHINA_TIME)
        articles = [digest.Article(f"AI event {i}", f"https://example.com/{i}",
                                   now - timedelta(hours=i + 1),
                                   "cn" if i < 3 else "global", f"source-{i}") for i in range(6)]
        with tempfile.TemporaryDirectory() as temp:
            source_file = Path(temp) / "sources.json"
            db_file = Path(temp) / "digest.sqlite3"
            source_file.write_text(json.dumps([{"name": "test", "kind": "rss", "region": "cn",
                                                "url": "https://example.com/feed"}]), encoding="utf-8")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test", "SERVERCHAN_SENDKEY": "SCT_test"}), \
                 patch.object(digest, "collect", return_value=articles), \
                 patch.object(digest, "deepseek_digest", side_effect=lambda stories, now: digest.fallback_digest(stories)), \
                 patch.object(digest, "send_serverchan") as send:
                self.assertEqual(digest.run(False, source_file, db_file), 0)
                self.assertEqual(digest.run(False, source_file, db_file), 0)
                self.assertEqual(send.call_count, 1)
            conn = sqlite3.connect(db_file)
            try:
                self.assertEqual(conn.execute("SELECT status FROM deliveries").fetchone()[0], "accepted")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sent_items").fetchone()[0], 5)
            finally:
                conn.close()

    def test_ambiguous_delivery_does_not_retry_automatically(self):
        now = datetime.now(digest.CHINA_TIME)
        article = digest.Article("OpenAI releases model", "https://example.com/one", now, "global", "test")
        with tempfile.TemporaryDirectory() as temp:
            source_file = Path(temp) / "sources.json"
            db_file = Path(temp) / "digest.sqlite3"
            source_file.write_text(json.dumps([{"name": "test", "kind": "rss", "region": "global",
                                                "url": "https://example.com/feed"}]), encoding="utf-8")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test", "SERVERCHAN_SENDKEY": "SCT_test"}), \
                 patch.object(digest, "collect", return_value=[article]), \
                 patch.object(digest, "deepseek_digest", side_effect=lambda stories, now: digest.fallback_digest(stories)), \
                 patch.object(digest, "send_serverchan", side_effect=digest.DeliveryUncertain("timeout")) as send:
                with self.assertRaises(digest.DeliveryUncertain):
                    digest.run(False, source_file, db_file)
                self.assertEqual(digest.run(False, source_file, db_file), 0)
                self.assertEqual(send.call_count, 1)
            conn = sqlite3.connect(db_file)
            try:
                self.assertEqual(conn.execute("SELECT status FROM deliveries").fetchone()[0], "uncertain")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
