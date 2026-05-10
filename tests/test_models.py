"""Tests for the Decision data model."""
import pytest
from datetime import datetime, timezone, timedelta
from anamne.models import Decision


def test_decision_defaults():
    d = Decision(
        content="Switched to Postgres",
        why="Need concurrent writes",
        source_type="commit",
        source_ref="abc12345",
        source_author="alice",
    )
    assert d.id  # auto-generated UUID
    assert d.confidence == 0.8
    assert d.file_paths == []
    assert d.keywords == []
    assert d.valid_until is None


def test_decision_is_stale_false_when_no_expiry():
    d = Decision(
        content="x", why="y", source_type="commit",
        source_ref="a", source_author="b",
    )
    assert d.is_stale() is False


def test_decision_is_stale_true_when_past():
    d = Decision(
        content="x", why="y", source_type="commit",
        source_ref="a", source_author="b",
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert d.is_stale() is True


def test_decision_is_stale_false_when_future():
    d = Decision(
        content="x", why="y", source_type="commit",
        source_ref="a", source_author="b",
        valid_until=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert d.is_stale() is False


def test_decision_short_ref():
    d = Decision(
        content="x", why="y", source_type="commit",
        source_ref="abcdef1234567890", source_author="b",
    )
    assert d.short_ref == "abcdef12"
    assert len(d.short_ref) == 8


def test_decision_short_ref_short_hash():
    d = Decision(
        content="x", why="y", source_type="commit",
        source_ref="abc", source_author="b",
    )
    assert d.short_ref == "abc"


def test_decision_to_dict():
    d = Decision(
        content="Used Redis for caching",
        why="DB reads were slow",
        source_type="commit",
        source_ref="deadbeef",
        source_author="bob",
        file_paths=["cache/redis.py"],
        keywords=["redis", "cache"],
    )
    result = d.to_dict()
    assert result["content"] == "Used Redis for caching"
    assert result["why"] == "DB reads were slow"
    assert result["file_paths"] == ["cache/redis.py"]
    assert result["keywords"] == ["redis", "cache"]
    assert "created_at" in result
    assert result["valid_until"] is None
