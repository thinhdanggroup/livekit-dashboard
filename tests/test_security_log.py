"""Tests for the failed-login security log store."""

from unittest.mock import patch

import app.services.security_log as sl


def test_list_failed_logins_empty(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        assert sl.list_failed_logins() == []


def test_log_failed_login_persists_newest_first(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("2.2.2.2", "root")
        entries = sl.list_failed_logins()
    assert entries[0]["ip"] == "2.2.2.2"
    assert entries[1]["ip"] == "1.1.1.1"


def test_count_by_ip_groups_and_sorts(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("2.2.2.2", "root")
        counts = sl.count_by_ip()
    assert counts["1.1.1.1"] == 2
    assert counts["2.2.2.2"] == 1
    assert list(counts) == ["1.1.1.1", "2.2.2.2"]


def test_log_failed_login_entry_shape(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        sl.log_failed_login("1.1.1.1", "admin")
        entry = sl.list_failed_logins()[0]
    assert set(entry) == {"ts", "ip", "username"}
    assert entry["ip"] == "1.1.1.1"
    assert entry["username"] == "admin"


def test_list_failed_logins_respects_limit(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        for i in range(5):
            sl.log_failed_login(f"10.0.0.{i}", "admin")
        assert len(sl.list_failed_logins(limit=2)) == 2


def test_count_by_ip_only_counts_recent_limit(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("2.2.2.2", "root")
        counts = sl.count_by_ip(limit=1)
    assert counts == {"2.2.2.2": 1}


def test_log_failed_login_never_raises(tmp_path):
    with patch.object(sl, "_STORE_PATH", "/nonexistent/path/s.json"):
        sl.log_failed_login("1.1.1.1", "admin")  # must not raise


def test_log_trims_to_max_entries(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")), patch.object(sl, "MAX_ENTRIES", 3):
        for i in range(5):
            sl.log_failed_login(f"10.0.0.{i}", "admin")
        entries = sl.list_failed_logins(limit=10)
    assert len(entries) == 3
    assert entries[0]["ip"] == "10.0.0.4"
