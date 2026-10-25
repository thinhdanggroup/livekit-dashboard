"""Tests for the webhook delivery log store."""

from unittest.mock import patch

import app.services.webhook_log as wl


def test_list_entries_empty(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")):
        assert wl.list_entries() == []


def test_log_delivery_persists_and_lists_newest_first(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")):
        wl.log_delivery("manual_test", "http://a", "{}", 200, None)
        entry_id = wl.log_delivery("alert", "http://b", "{}", None, "timeout")
        entries = wl.list_entries()
    assert len(entries) == 2
    assert entries[0]["source"] == "alert"  # newest first
    assert entries[0]["id"] == entry_id


def test_get_entry_found_and_missing(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")):
        entry_id = wl.log_delivery("manual_test", "http://a", "{}", 200, None)
        assert wl.get_entry(entry_id)["url"] == "http://a"
        assert wl.get_entry("doesnotexist") is None


def test_log_trims_to_max_entries(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")), patch.object(wl, "MAX_ENTRIES", 3):
        for i in range(5):
            wl.log_delivery("manual_test", f"http://{i}", "{}", 200, None)
        assert len(wl.list_entries(limit=10)) == 3
