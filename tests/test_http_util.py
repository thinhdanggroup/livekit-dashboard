import io
import urllib.error

from app.utils.http import post_json


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


def test_post_json_success(monkeypatch):
    def fake_urlopen(req, timeout):
        return _FakeResponse(b"ok", status=200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = post_json("http://example.com", "{}")

    assert result == {"status": 200, "body": "ok", "error": None}


def test_post_json_success_truncates_body(monkeypatch):
    def fake_urlopen(req, timeout):
        return _FakeResponse(b"x" * 2000, status=200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = post_json("http://example.com", "{}")

    assert len(result["body"]) == 512


def test_post_json_sends_post_with_headers_and_payload(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["method"] = req.get_method()
        captured["data"] = req.data
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["timeout"] = timeout
        return _FakeResponse(b"", status=204)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    post_json("http://example.com/hook", '{"a": 1}')

    assert captured["method"] == "POST"
    assert captured["data"] == b'{"a": 1}'
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["headers"]["user-agent"] == "livekit-dashboard/1.0"
    assert captured["timeout"] == 5.0


def test_post_json_http_error(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            "http://example.com", 404, "Not Found", {}, io.BytesIO(b"nope")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = post_json("http://example.com", "{}")

    assert result["status"] == 404
    assert result["body"] == "nope"
    assert result["error"] is None


def test_post_json_http_error_body_truncated_to_256(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            "http://example.com", 500, "Server Error", {}, io.BytesIO(b"e" * 1000)
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = post_json("http://example.com", "{}")

    assert result["status"] == 500
    assert len(result["body"]) == 256


def test_post_json_connection_error(monkeypatch):
    def fake_urlopen(req, timeout):
        raise OSError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = post_json("http://example.com", "{}")

    assert result["status"] is None
    assert result["body"] == ""
    assert "Connection refused" in result["error"]
