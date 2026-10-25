"""Tests for the IP allowlist store.

This store backs a middleware (added in a later task) that calls
is_allowed(ip) on every request and 403s on False. The critical safety
property tested here is that save_allowlist() can never produce a
non-empty list that excludes the requester's own IP -- that would let
an operator lock themselves out with no recovery path short of editing
the server's filesystem directly.
"""

from unittest.mock import patch

import app.services.ip_allowlist as ipa


def test_get_allowlist_defaults_empty(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        assert ipa.get_allowlist() == []


def test_is_allowed_true_when_list_empty(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        assert ipa.is_allowed("9.9.9.9") is True


def test_save_allowlist_includes_requester_ip(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        result = ipa.save_allowlist("203.0.113.5", requester_ip="198.51.100.9")
    assert "203.0.113.5" in result
    assert "198.51.100.9" in result


def test_save_blank_allowlist_clears_to_allow_all(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        ipa.save_allowlist("203.0.113.5", requester_ip="198.51.100.9")
        result = ipa.save_allowlist("", requester_ip="198.51.100.9")
        assert ipa.is_allowed("9.9.9.9") is True
    assert result == []


def test_is_allowed_checks_membership_after_save(tmp_path):
    # NOTE: the task brief's literal transcription of this test has the two
    # assertions outside the `with` block, which would check the unpatched
    # default _STORE_PATH instead of the store just written to -- defeating
    # the test's purpose. Keeping the assertions inside the block is what
    # actually verifies "is_allowed checks membership after save".
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        ipa.save_allowlist("203.0.113.5", requester_ip="203.0.113.5")
        assert ipa.is_allowed("203.0.113.5") is True
        assert ipa.is_allowed("9.9.9.9") is False


def test_save_allowlist_no_duplicate_when_requester_already_present(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        result = ipa.save_allowlist(
            "203.0.113.5, 198.51.100.9", requester_ip="198.51.100.9"
        )
    assert result.count("198.51.100.9") == 1
    assert sorted(result) == ["198.51.100.9", "203.0.113.5"]


def test_save_blank_whitespace_only_also_clears(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        ipa.save_allowlist("203.0.113.5", requester_ip="198.51.100.9")
        result = ipa.save_allowlist("   ", requester_ip="198.51.100.9")
    assert result == []
    assert ipa.is_allowed("198.51.100.9") is True
    assert ipa.is_allowed("9.9.9.9") is True


def test_save_allowlist_parses_whitespace_and_double_commas(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        result = ipa.save_allowlist(
            "1.1.1.1, 2.2.2.2 ,, 3.3.3.3", requester_ip="1.1.1.1"
        )
    assert sorted(result) == ["1.1.1.1", "2.2.2.2", "3.3.3.3"]
    assert "" not in result


def test_save_allowlist_drops_duplicates_in_raw_input(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        result = ipa.save_allowlist(
            "1.1.1.1, 1.1.1.1, 2.2.2.2", requester_ip="1.1.1.1"
        )
    assert sorted(result) == ["1.1.1.1", "2.2.2.2"]


def test_save_allowlist_strips_whitespace_from_requester_ip(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        result = ipa.save_allowlist(
            "203.0.113.5", requester_ip="  203.0.113.5  "
        )
    assert result == ["203.0.113.5"]
    assert result.count("203.0.113.5") == 1


def test_get_allowlist_persists_across_calls(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        ipa.save_allowlist("203.0.113.5", requester_ip="198.51.100.9")
        result = ipa.get_allowlist()
    assert sorted(result) == ["198.51.100.9", "203.0.113.5"]
