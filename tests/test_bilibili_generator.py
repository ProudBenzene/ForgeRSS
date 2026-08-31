from datetime import datetime
import xml.etree.ElementTree as ET

import pytest
import pytz

from generators.base import Article
from generators.social.bilibili import generator as bilibili_module
from generators.social.bilibili.generator import (
    BilibiliUPGenerator,
    _parse_bilibili_publish_time,
)


SHANGHAI = pytz.timezone("Asia/Shanghai")
NOW = SHANGHAI.localize(datetime(2026, 8, 31, 12, 0))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-08-15", datetime(2025, 8, 14, 16, 0, tzinfo=pytz.UTC)),
        ("08-15", datetime(2026, 8, 14, 16, 0, tzinfo=pytz.UTC)),
        ("12-31", datetime(2025, 12, 30, 16, 0, tzinfo=pytz.UTC)),
        ("刚刚", datetime(2026, 8, 31, 4, 0, tzinfo=pytz.UTC)),
        ("刚才", datetime(2026, 8, 31, 4, 0, tzinfo=pytz.UTC)),
        ("昨天", datetime(2026, 8, 30, 4, 0, tzinfo=pytz.UTC)),
        ("15分钟前", datetime(2026, 8, 31, 3, 45, tzinfo=pytz.UTC)),
        ("3小时前", datetime(2026, 8, 31, 1, 0, tzinfo=pytz.UTC)),
        ("7天前", datetime(2026, 8, 24, 4, 0, tzinfo=pytz.UTC)),
    ],
)
def test_parse_bilibili_publish_time(value, expected):
    assert _parse_bilibili_publish_time(value, now=NOW) == expected


def test_invalid_publish_time_falls_back_to_now():
    assert _parse_bilibili_publish_time("未知", now=NOW) == NOW.astimezone(pytz.UTC)


def test_naive_now_is_interpreted_as_shanghai_time():
    naive_now = datetime(2026, 8, 31, 12, 0)
    assert _parse_bilibili_publish_time("刚刚", now=naive_now) == datetime(
        2026, 8, 31, 4, 0, tzinfo=pytz.UTC
    )


class FakeBrowser:
    def __init__(self):
        self.waits = []
        self.was_quit = False

    def wait(self, seconds):
        self.waits.append(seconds)

    def quit(self):
        self.was_quit = True


def _article(mid, up_name):
    return Article(
        url=f"https://www.bilibili.com/video/BV{mid}",
        title=f"[{up_name}] Test video",
        published_at=NOW.astimezone(pytz.UTC),
        content="<p>Test video</p>",
        author=up_name,
        category="Video",
    )


def _mock_ready_browser(monkeypatch):
    browser = FakeBrowser()
    monkeypatch.setattr(
        bilibili_module, "check_bilibili_ready", lambda: (True, "Ready")
    )
    monkeypatch.setattr(
        bilibili_module, "create_bilibili_browser", lambda headless=False: browser
    )
    monkeypatch.setattr(
        bilibili_module, "verify_bilibili_login", lambda browser: True
    )
    return browser


def test_normalize_mids_validates_and_deduplicates():
    assert BilibiliUPGenerator._normalize_mids(
        ["475304452", " 106320250 ", "475304452", ""]
    ) == ["475304452", "106320250"]

    with pytest.raises(ValueError, match="digits only"):
        BilibiliUPGenerator._normalize_mids(["../../profile"])


def test_numeric_environment_options_are_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "-1")
    with pytest.raises(ValueError, match="must not be negative"):
        BilibiliUPGenerator(mids=["111"], base_dir=tmp_path)

    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "0")
    monkeypatch.setenv("BILIBILI_MAX_VIDEOS_DAILY", "0")
    with pytest.raises(ValueError, match="must be greater than zero"):
        BilibiliUPGenerator(mids=["111"], base_dir=tmp_path)


def test_history_mode_defaults_to_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "0")
    monkeypatch.setenv("BILIBILI_MAX_VIDEOS_DAILY", "20")
    monkeypatch.setenv("BILIBILI_HISTORY_MODE", "true")
    generator = BilibiliUPGenerator(mids=["111"], base_dir=tmp_path)
    assert generator.HISTORY_MODE is True


def test_feed_keeps_one_clickable_cover_without_duplicate_video_links(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "0")
    monkeypatch.delenv("BILIBILI_LEGACY_FEED_MID", raising=False)
    generator = BilibiliUPGenerator(mids=["111"], base_dir=tmp_path)
    video_url = "https://www.bilibili.com/video/BV111"
    cover_url = "https://i0.hdslb.com/bfs/archive/cover.jpg"
    article = Article(
        url=video_url,
        title="[Test UP] Test video",
        published_at=NOW.astimezone(pytz.UTC),
        summary="Test video | Views: 100 | 01:23",
        content=(
            f'<div><a href="{video_url}"><img src="{cover_url}" /></a></div>'
            '<p><strong>UP Master:</strong> Test UP</p>'
            '<p><strong>Views:</strong> 100 | <strong>Duration:</strong> 01:23</p>'
            f'<p><a href="{video_url}">Watch Video</a></p>'
        ),
        author="Test UP",
        category="Video",
    )

    output = generator._store_mid_feed(
        mid="111",
        up_name="Test UP",
        new_articles=[article],
        full_refresh=True,
        max_articles=10,
        use_db=False,
    )
    item_content = ET.parse(output).findtext("./channel/item/description")

    assert item_content.count(f'<a href="{video_url}"') == 1
    assert item_content.count(f'<img src="{cover_url}"') == 1
    assert "Watch Video" not in item_content
    assert "View Original" not in item_content
    assert "<video" not in item_content
    assert "<iframe" not in item_content
    assert "<enclosure" not in item_content


def test_run_writes_one_feed_and_cache_per_mid(tmp_path, monkeypatch):
    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "0")
    monkeypatch.setenv("BILIBILI_LEGACY_FEED_MID", "111")
    browser = _mock_ready_browser(monkeypatch)
    generator = BilibiliUPGenerator(
        mids=["111", "222"], base_dir=tmp_path
    )

    def fetch(_browser, mid, **_kwargs):
        up_name = f"UP {mid}"
        return up_name, [_article(mid, up_name)]

    monkeypatch.setattr(generator, "_fetch_up_videos", fetch)

    assert generator.run(max_articles=10, use_db=False)
    assert browser.was_quit
    assert (tmp_path / "cache" / "bilibili_up_111.json").exists()
    assert (tmp_path / "cache" / "bilibili_up_222.json").exists()

    first_feed = tmp_path / "feeds" / "feed_bilibili_up_111.xml"
    second_feed = tmp_path / "feeds" / "feed_bilibili_up_222.xml"
    legacy_feed = tmp_path / "feeds" / "feed_bilibili_up.xml"
    assert first_feed.exists()
    assert second_feed.exists()
    assert first_feed.stat().st_mode & 0o777 == 0o644
    assert second_feed.stat().st_mode & 0o777 == 0o644
    assert legacy_feed.read_bytes() == first_feed.read_bytes()
    assert legacy_feed.stat().st_mode & 0o777 == 0o644
    assert ET.parse(first_feed).findtext("./channel/title") == "UP 111 的 Bilibili 投稿"
    assert ET.parse(second_feed).findtext("./channel/title") == "UP 222 的 Bilibili 投稿"
    assert generator.FEED_NAME == "bilibili_up"


def test_one_mid_failure_does_not_discard_other_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "0")
    monkeypatch.delenv("BILIBILI_LEGACY_FEED_MID", raising=False)
    browser = _mock_ready_browser(monkeypatch)
    generator = BilibiliUPGenerator(
        mids=["111", "222"], base_dir=tmp_path
    )

    def fetch(_browser, mid, **_kwargs):
        if mid == "222":
            raise RuntimeError("simulated page failure")
        return "Working UP", [_article(mid, "Working UP")]

    monkeypatch.setattr(generator, "_fetch_up_videos", fetch)

    assert not generator.run(max_articles=10, use_db=False)
    assert browser.was_quit
    assert (tmp_path / "feeds" / "feed_bilibili_up_111.xml").exists()
    assert not (tmp_path / "feeds" / "feed_bilibili_up_222.xml").exists()


def test_empty_refresh_preserves_existing_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("BILIBILI_UP_DELAY_SECONDS", "0")
    monkeypatch.delenv("BILIBILI_LEGACY_FEED_MID", raising=False)
    _mock_ready_browser(monkeypatch)
    generator = BilibiliUPGenerator(mids=["111"], base_dir=tmp_path)
    monkeypatch.setattr(
        generator,
        "_fetch_up_videos",
        lambda *_args, **_kwargs: ("Stable UP", [_article("111", "Stable UP")]),
    )
    assert generator.run(max_articles=10, use_db=False)

    feed = tmp_path / "feeds" / "feed_bilibili_up_111.xml"
    original = feed.read_bytes()
    monkeypatch.setattr(
        generator,
        "_fetch_up_videos",
        lambda *_args, **_kwargs: ("Stable UP", []),
    )

    assert not generator.run(max_articles=10, use_db=False)
    assert feed.read_bytes() == original
