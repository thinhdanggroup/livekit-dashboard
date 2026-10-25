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


# --- Corrupt/unreadable store: must always fail OPEN (allow-all), never deny. ---
#
# A bug here is exactly the failure mode this whole feature exists to
# prevent: a misconfigured or corrupted store denying every request with
# no recovery path short of editing the server's filesystem directly.


def test_get_allowlist_directory_at_path_fails_open(tmp_path):
    """A directory at the store path (e.g. an unmounted Docker bind-mount
    target) must not raise -- it must be treated as allow-all."""
    store_path = tmp_path / "a.json"
    store_path.mkdir()
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True


def test_get_allowlist_malformed_json_fails_open(tmp_path):
    store_path = tmp_path / "a.json"
    store_path.write_text("{not valid json")
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True


def test_get_allowlist_non_utf8_bytes_fails_open(tmp_path):
    store_path = tmp_path / "a.json"
    store_path.write_bytes(b"\xff\xfe\x00\x01not utf-8")
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True


def test_get_allowlist_bare_list_shape_fails_open(tmp_path):
    """A JSON file that's just `[]` (not the expected {"ips": [...]} dict)."""
    store_path = tmp_path / "a.json"
    store_path.write_text("[]")
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True


def test_get_allowlist_null_ips_fails_open(tmp_path):
    store_path = tmp_path / "a.json"
    store_path.write_text('{"ips": null}')
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True


def test_get_allowlist_string_ips_does_not_explode_to_chars(tmp_path):
    """{"ips": "1.2.3.4"} must not be list()-exploded into single-character
    "IPs" (which would deny everyone except requests from a 1-char IP)."""
    store_path = tmp_path / "a.json"
    store_path.write_text('{"ips": "1.2.3.4"}')
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True


def test_get_allowlist_non_string_items_fails_open(tmp_path):
    store_path = tmp_path / "a.json"
    store_path.write_text('{"ips": [1, 2, 3]}')
    with patch.object(ipa, "_STORE_PATH", str(store_path)):
        assert ipa.get_allowlist() == []
        assert ipa.is_allowed("9.9.9.9") is True
