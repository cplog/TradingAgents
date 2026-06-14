"""Tests for the Reddit ticker fetcher."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.reddit import (
    _parse_rss_entry,
    fetch_reddit_feed_items,
    fetch_reddit_posts,
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
    <published>2026-06-11T15:57:59Z</published>
    <updated>2026-06-11T15:57:59Z</updated>
    <link href="https://www.reddit.com/r/wallstreetbets/comments/1u332lz/rss_nvda_post/"/>
    <content type="html">&lt;p&gt;I like NVDA.&lt;/p&gt;</content>
    <author><name>/u/trader</name></author>
  </entry>
</feed>
"""


@pytest.mark.unit
class TestFetchRedditPosts:
    @patch("tradingagents.dataflows.reddit.urlopen")
    def test_json_success_returns_formatted_block(self, mock_urlopen):
        posts = [
            {
                "id": "abc",
                "title": "NVDA to the moon",
                "selftext": "Bullish on NVDA.",
                "score": 400,
                "num_comments": 200,
                "created_utc": 1749682800,
                "permalink": "/r/wallstreetbets/comments/abc/nvda_to_the_moon/",
            }
        ]
        mock_urlopen.return_value = _FakeResponse(_json_payload(posts))

        result = fetch_reddit_posts("NVDA", subreddits=["wallstreetbets"])
        assert "NVDA to the moon" in result
        assert "400↑" in result
        assert "200c" in result
        assert "Bullish on NVDA." in result

    @patch("tradingagents.dataflows.reddit.urlopen")
    def test_json_blocked_falls_back_to_rss(self, mock_urlopen):
        from urllib.error import HTTPError

        # First call (JSON) raises 403; second call (RSS) succeeds.
        json_error = HTTPError(
            "https://www.reddit.com/r/wallstreetbets/search.json",
            403,
            "Blocked",
            {},
            None,
        )
        mock_urlopen.side_effect = [json_error, _FakeResponse(RSS_BODY)]

        result = fetch_reddit_posts("NVDA", subreddits=["wallstreetbets"])
        assert "RSS NVDA post" in result
        assert "I like NVDA." in result
        # RSS lacks engagement counts.
        assert "?↑" in result or "?c" in result

    @patch("tradingagents.dataflows.reddit.urlopen")
    def test_no_posts_returns_placeholder(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(_json_payload([]))

        result = fetch_reddit_posts("NVDA", subreddits=["wallstreetbets"])
        assert "no Reddit posts found" in result

    @patch("tradingagents.dataflows.reddit.urlopen")
    def test_feed_items_structured_output(self, mock_urlopen):
        posts = [
            {
                "id": "abc",
                "title": "NVDA to the moon",
                "selftext": "Bullish.",
                "score": 10,
                "num_comments": 5,
                "created_utc": 1749682800,
                "permalink": "/r/wallstreetbets/comments/abc/nvda_to_the_moon/",
            }
        ]
        mock_urlopen.return_value = _FakeResponse(_json_payload(posts))

        items = fetch_reddit_feed_items("NVDA", subreddits=["wallstreetbets"])
        assert len(items) == 1
        assert items[0]["title"] == "NVDA to the moon"
        assert items[0]["publisher"] == "r/wallstreetbets"
        assert "reddit.com" in items[0]["link"]


@pytest.mark.unit
class TestParseRssEntry:
    def test_extracts_title_content_and_link(self):
        import xml.etree.ElementTree as ET

        entry = ET.fromstring(
            """
            <entry xmlns="http://www.w3.org/2005/Atom">
              <title>Hello &amp; NVDA</title>
              <published>2026-06-11T15:57:59Z</published>
              <link href="https://reddit.com/r/wsb/comments/x/foo/"/>
              <content type="html">&lt;p&gt;Body text.&lt;/p&gt;</content>
            </entry>
            """
        )
        data = _parse_rss_entry(entry)
        assert data["title"] == "Hello & NVDA"
        assert data["selftext"] == "Body text."
        assert data["permalink"] == "https://reddit.com/r/wsb/comments/x/foo/"
        assert data["created_utc"] == 1781193479.0
        assert data["score"] is None
        assert data["num_comments"] is None
