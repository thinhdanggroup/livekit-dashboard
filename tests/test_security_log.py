"""Tests for the failed-login security log store."""

from concurrent.futures import ThreadPoolExecutor
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


# --- Corrupt/unreadable store: must degrade to [] gracefully, never 500. ---
#
# The /settings page renders this log -- it must never 500 on a corrupt
# security_log.json, since that page is also where an operator would go
# to fix an allowlist problem.


def test_list_failed_logins_directory_at_path_degrades_gracefully(tmp_path):
    """A directory at the store path (e.g. an unmounted Docker bind-mount
    target) must not raise -- it must be treated as an empty log."""
    store_path = tmp_path / "s.json"
    store_path.mkdir()
    with patch.object(sl, "_STORE_PATH", str(store_path)):
        assert sl.list_failed_logins() == []
        assert sl.count_by_ip() == {}


def test_list_failed_logins_malformed_json_degrades_gracefully(tmp_path):
    store_path = tmp_path / "s.json"
    store_path.write_text("{not valid json")
    with patch.object(sl, "_STORE_PATH", str(store_path)):
        assert sl.list_failed_logins() == []


def test_list_failed_logins_non_utf8_bytes_degrades_gracefully(tmp_path):
    store_path = tmp_path / "s.json"
    store_path.write_bytes(b"\xff\xfe\x00\x01not utf-8")
    with patch.object(sl, "_STORE_PATH", str(store_path)):
        assert sl.list_failed_logins() == []


def test_list_failed_logins_non_list_shape_degrades_gracefully(tmp_path):
    """A JSON value that isn't a list (e.g. a bare object) must be treated
    as an empty log rather than raising when iterated over."""
    store_path = tmp_path / "s.json"
    store_path.write_text('{"not": "a list"}')
    with patch.object(sl, "_STORE_PATH", str(store_path)):
        assert sl.list_failed_logins() == []
        assert sl.count_by_ip() == {}


def test_missing_security_log_store_logs_no_warning(tmp_path, caplog):
    """A never-configured (missing) store is the normal state for a fresh
    install -- it must not log a warning."""
    store_path = tmp_path / "does_not_exist.json"
    with caplog.at_level("WARNING", logger="app.services.security_log"):
        with patch.object(sl, "_STORE_PATH", str(store_path)):
            assert sl.list_failed_logins() == []
    assert caplog.records == []


def test_genuinely_corrupt_security_log_store_logs_warning(tmp_path, caplog):
    store_path = tmp_path / "s.json"
    store_path.write_text("{not valid json")
    with caplog.at_level("WARNING", logger="app.services.security_log"):
        with patch.object(sl, "_STORE_PATH", str(store_path)):
            assert sl.list_failed_logins() == []
    assert len(caplog.records) == 1
    assert "unreadable" in caplog.records[0].message


def test_log_trims_to_max_entries(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")), patch.object(sl, "MAX_ENTRIES", 3):
        for i in range(5):
            sl.log_failed_login(f"10.0.0.{i}", "admin")
        entries = sl.list_failed_logins(limit=10)
    assert len(entries) == 3
    assert entries[0]["ip"] == "10.0.0.4"


def test_log_failed_login_survives_concurrent_writes(tmp_path):
    """Reproduces the reviewer's finding: requires_admin runs sync dependencies
    in a threadpool, so concurrent failed-login attempts call
    log_failed_login from multiple real OS threads at once. Without a lock
    around the load-append-save sequence and an atomic write, this is a
    classic read-modify-write race that drops nearly all entries (the
    reviewer saw 200 concurrent requests leave only 1 entry).

    Uses a raised MAX_ENTRIES (bigger than the concurrent count) so the
    assertion can require an EXACT count rather than a fuzzy "close to"
    bound, and real threads (ThreadPoolExecutor), not asyncio tasks, to
    match how requires_admin actually calls this function.
    """
    n = 200
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")), patch.object(sl, "MAX_ENTRIES", 1000):
        with ThreadPoolExecutor(max_workers=32) as pool:
            futures = [pool.submit(sl.log_failed_login, f"10.0.{i // 256}.{i % 256}", "admin") for i in range(n)]
            for f in futures:
                f.result()
        entries = sl.list_failed_logins(limit=n + 10)
    assert len(entries) == n
