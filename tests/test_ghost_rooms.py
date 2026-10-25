"""Tests for the ghost room tracker service."""

from unittest.mock import patch

import app.services.ghost_rooms as gr


def test_record_poll_no_change_returns_no_ghosts(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
        ghosts = gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
    assert ghosts == []


def test_room_disappearing_becomes_ghost(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": "m"}])
        ghosts = gr.record_poll([])  # r1 is gone
    assert len(ghosts) == 1
    assert ghosts[0]["name"] == "r1"
    assert ghosts[0]["closed_minutes_ago"] == 0


def test_room_recreated_is_not_a_ghost(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
        gr.record_poll([])  # r1 ends -> ghost
        ghosts = gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 2, "metadata": ""}])  # r1 live again
    assert ghosts == []  # live entries are never also shown as ghosts


def test_ghosts_older_than_ttl_are_pruned(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")), patch.object(gr, "TTL_MINUTES", 0):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
        gr.record_poll([])  # ghost created, immediately older than a 0-minute TTL
        ghosts = gr.record_poll([])  # next poll should prune it
    assert ghosts == []
