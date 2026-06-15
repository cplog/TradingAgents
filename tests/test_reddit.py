"""Tests for the Reddit ticker fetcher."""

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from tradingagents.dataflows.reddit import (
    fetch_reddit_feed_items,
    fetch_reddit_posts,
    search_reddit,
)


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _json_payload(posts):
    return json.dumps({"data": {"children": [{"data": p} for p in posts]}}).encode("utf-8")


RSS_BODY = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>test</title>
  <entry>
    <title>RSS NVDA post</title>
    <updated>2026-06-11T15:57:59Z</updated>
    <link href="https://www.reddit.com/r/wallstreetbets/comments/1u332lz/rss_nvda_post/"/>
    <author><name>/u/trader</name></author>
  </entry>
</feed>
"""


@pytest.mark.unit
class TestSearchReddit:
    @patch("tradingagents.dataflows.reddit._fetch_subreddit_rss")
    @patch("tradingagents.dataflows.reddit._fetch_subreddit_json")
    def test_search_reddit_returns_plaintext(self, mock_json, mock_rss):
        mock_rss.return_value = [
            {
                "id": "abc",
                "title": "NVDA to the moon",
                "score": 400,
                "num_comments": 200,
                "created_utc": 1749682800,
                "permalink": "/r/wallstreetbets/comments/abc/nvda_to_the_moon/",
                "author": "trader",
                "subreddit": "wallstreetbets",
                "_source": "rss",
            }
        ]
        result = search_reddit("NVDA", subreddits=["wallstreetbets"])
        assert "NVDA to the moon" in result
        assert "NVDA" in result

    @patch("tradingagents.dataflows.reddit._fetch_subreddit_rss")
    @patch("tradingagents.dataflows.reddit._fetch_subreddit_json")
    def test_no_posts_returns_placeholder(self, mock_json, mock_rss):
        mock_rss.return_value = []
        mock_json.return_value = []
        result = search_reddit("NVDA", subreddits=["wallstreetbets"])
        assert "No Reddit discussions found" in result


@pytest.mark.unit
class TestBackwardCompatAliases:
    @patch("tradingagents.dataflows.reddit._fetch_subreddit_rss")
    @patch("tradingagents.dataflows.reddit._fetch_subreddit_json")
    def test_fetch_reddit_posts_string(self, mock_json, mock_rss):
        mock_rss.return_value = [
            {
                "id": "x",
                "title": "Test post",
                "score": 0,
                "num_comments": 0,
                "created_utc": 1749682800,
                "permalink": "/r/test/comments/x/t/",
                "author": "u",
                "subreddit": "test",
                "_source": "rss",
            }
        ]
        result = fetch_reddit_posts("AAPL", subreddits=["test"])
        assert isinstance(result, str)
        assert "Test post" in result

    @patch("tradingagents.dataflows.reddit._fetch_subreddit_rss")
    @patch("tradingagents.dataflows.reddit._fetch_subreddit_json")
    def test_fetch_feed_items_structured(self, mock_json, mock_rss):
        mock_rss.return_value = [
            {
                "id": "y",
                "title": "Structured post",
                "score": 10,
                "num_comments": 5,
                "created_utc": 1749682800,
                "permalink": "/r/test/comments/y/s/",
                "author": "u2",
                "subreddit": "test",
                "_source": "rss",
            }
        ]
        items = fetch_reddit_feed_items("AAPL", subreddits=["test"])
        assert isinstance(items, list)
        assert len(items) == 1
        assert items[0]["title"] == "Structured post"
