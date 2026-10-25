"""Tests for the /analytics/latency route.

Each test calls ls._reset_for_tests() first since the latency sample
store is module-level state that otherwise leaks between tests --
other tests in the suite exercise routes that record real samples
(e.g. list_rooms -> "api_list_rooms"), which would make the
"empty state" assertions flaky depending on test order.
"""

import app.services.latency_samples as ls


def test_latency_page_requires_auth(client):
    resp = client.get("/analytics/latency", follow_redirects=False)
    assert resp.status_code == 401


def test_latency_page_empty_state(client, auth_headers):
    ls._reset_for_tests()
    resp = client.get("/analytics/latency", headers=auth_headers)
    assert resp.status_code == 200
    assert b"No latency data" in resp.content or b"no data" in resp.content.lower()


def test_latency_page_shows_percentiles(client, auth_headers):
    ls._reset_for_tests()
    for v in [10, 20, 30]:
        ls.record("api_list_rooms", float(v))
    resp = client.get("/analytics/latency?window=24h", headers=auth_headers)
    assert resp.status_code == 200
    assert b"api_list_rooms" in resp.content
    assert b"P50" in resp.content


def test_latency_page_default_window_is_1h(client, auth_headers):
    ls._reset_for_tests()
    resp = client.get("/analytics/latency", headers=auth_headers)
    assert resp.status_code == 200
    assert b"1h" in resp.content


def test_latency_page_window_24h_excludes_old_samples(client, auth_headers):
    ls._reset_for_tests()
    import time

    ls.record("api_list_rooms", 999.0, ts=time.time() - 100000)  # outside 24h window
    resp = client.get("/analytics/latency?window=24h", headers=auth_headers)
    assert resp.status_code == 200
    # op_type exists (list_op_types still reports it has samples ever recorded)
    # but the stats for the 24h window should show no data for it.
    assert b"no data" in resp.content.lower() or b"No latency data" in resp.content


def test_latency_page_slowest_sorted_descending(client, auth_headers):
    ls._reset_for_tests()
    ls.record("rtc_connect", 5.0)
    ls.record("rtc_connect", 50.0)
    ls.record("rtc_connect", 25.0)
    resp = client.get("/analytics/latency?window=1h", headers=auth_headers)
    assert resp.status_code == 200
    text = resp.content.decode()
    table_text = text[text.find("Slowest recent operations"):]
    pos_50 = table_text.find("50.0")
    pos_25 = table_text.find("25.0")
    pos_5 = table_text.find("5.0")
    assert pos_50 != -1 and pos_25 != -1 and pos_5 != -1
    assert pos_50 < pos_25 < pos_5
