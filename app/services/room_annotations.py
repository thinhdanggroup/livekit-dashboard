"""JSON file-backed store for room notes, tags, and pinned state."""

import json
import os
from typing import Dict, List

_STORE_PATH = os.environ.get("ROOM_ANNOTATIONS_FILE", "/tmp/room_annotations.json")

PRESET_TAGS = ["prod", "demo", "support", "VIP"]


def _load() -> dict:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"pinned": [], "notes": {}, "tags": {}}


def _save(data: dict) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_pinned() -> List[str]:
    return _load().get("pinned", [])


def pin_room(room_name: str) -> None:
    data = _load()
    if room_name not in data["pinned"]:
        data["pinned"].append(room_name)
    _save(data)


def unpin_room(room_name: str) -> None:
    data = _load()
    data["pinned"] = [r for r in data["pinned"] if r != room_name]
    _save(data)


def get_annotations(room_name: str) -> dict:
    data = _load()
    return {
        "note": data.get("notes", {}).get(room_name, ""),
        "tags": data.get("tags", {}).get(room_name, []),
        "pinned": room_name in data.get("pinned", []),
    }


def set_annotations(room_name: str, note: str, tags: List[str]) -> None:
    data = _load()
    if "notes" not in data:
        data["notes"] = {}
    if "tags" not in data:
        data["tags"] = {}
    data["notes"][room_name] = note
    data["tags"][room_name] = tags
    _save(data)


def get_all_annotations() -> dict:
    return _load()


def build_timeline(room, participants: list) -> list:
    """Build a synthetic timeline from current room + participant state."""
    events = []

    if room and getattr(room, "creation_time", None):
        events.append({
            "ts": room.creation_time,
            "kind": "room_created",
            "label": "Room created",
            "icon": "bi-door-open",
            "color": "success",
        })

    for p in participants:
        joined_at = getattr(p, "joined_at", None)
        identity = getattr(p, "identity", "unknown")
        name = getattr(p, "name", "") or identity

        if joined_at:
            events.append({
                "ts": joined_at,
                "kind": "participant_joined",
                "label": f"{name} joined",
                "icon": "bi-person-plus",
                "color": "primary",
                "identity": identity,
            })

        for track in getattr(p, "tracks", []):
            sid = getattr(track, "sid", "")
            track_type = getattr(track, "type", 0)
            muted = getattr(track, "muted", False)
            kind = "video" if track_type == 1 else "audio"
            icon = "bi-camera-video" if kind == "video" else "bi-mic"
            if muted:
                events.append({
                    "ts": joined_at,
                    "kind": "track_muted",
                    "label": f"{name} {kind} muted",
                    "icon": "bi-mic-mute",
                    "color": "warning",
                    "identity": identity,
                })
            else:
                events.append({
                    "ts": joined_at,
                    "kind": "track_published",
                    "label": f"{name} published {kind}",
                    "icon": icon,
                    "color": "info",
                    "identity": identity,
                })

    events.sort(key=lambda e: e.get("ts") or 0)
    return events
