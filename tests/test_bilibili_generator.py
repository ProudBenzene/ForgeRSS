from datetime import datetime

import pytest
import pytz

from generators.social.bilibili.generator import _parse_bilibili_publish_time


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
