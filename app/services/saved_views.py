"""JSON file-backed store for saved dashboard filter views."""

import json
import os
import uuid
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import quote


_STORE_PATH = os.environ.get("SAVED_VIEWS_FILE", "/tmp/saved_views.json")


@dataclass
class SavedView:
    id: str
    name: str
    time_range: str = ""
    q: str = ""
    sort: str = "desc"
    sort_by: str = "created_at"

    def as_dict(self) -> dict:
        return asdict(self)

    def as_query_string(self) -> str:
        """Serialize non-default fields as a URL query string."""
        parts = []
        if self.time_range:
            parts.append(f"time_range={self.time_range}")
        if self.q:
            parts.append(f"q={quote(self.q)}")
        if self.sort != "desc":
            parts.append(f"sort={self.sort}")
        if self.sort_by != "created_at":
            parts.append(f"sort_by={self.sort_by}")
        return "&".join(parts)


def _load() -> list:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(views: list) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(views, f, indent=2)


def list_views() -> list[SavedView]:
    return [SavedView(**v) for v in _load()]


def get_view(view_id: str) -> Optional[SavedView]:
    for v in _load():
        if v["id"] == view_id:
            return SavedView(**v)
    return None


def create_view(
    name: str,
    time_range: str = "",
    q: str = "",
    sort: str = "desc",
    sort_by: str = "created_at",
) -> SavedView:
    views = _load()
    view = SavedView(
        id=str(uuid.uuid4())[:8],
        name=name.strip(),
        time_range=time_range,
        q=q.strip(),
        sort=sort,
        sort_by=sort_by,
    )
    views.append(view.as_dict())
    _save(views)
    return view


def delete_view(view_id: str) -> bool:
    views = _load()
    new_views = [v for v in views if v["id"] != view_id]
    if len(new_views) == len(views):
        return False
    _save(new_views)
    return True
