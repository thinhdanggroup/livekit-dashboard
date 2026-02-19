"""Homer/SIPCAPTURE SIP monitoring routes."""

import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token
from app.services.homer import HomerClient, get_homer_client

router = APIRouter()

_HOMER_ENABLED = lambda: os.environ.get("ENABLE_HOMER", "false").lower() == "true"  # noqa: E731


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _group_calls(records: list[dict]) -> list[dict]:
    """
    Group raw Homer search records by callid and build a summary row per call.
    Returns a list of summary dicts sorted newest-first.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        cid = rec.get("callid") or rec.get("call_id") or ""
        groups[cid].append(rec)

    rows: list[dict] = []
    for cid, recs in groups.items():
        # Pick INVITE record first, else the first record
        invite = next((r for r in recs if r.get("method") == "INVITE"), recs[0])

        methods = list({r.get("method", "") for r in recs if r.get("method")})
        method_strs = sorted(methods)

        # Status derivation
        all_methods = {r.get("method", "") for r in recs}
        response_codes = {str(r.get("response_code", "")) for r in recs}
        # Homer sometimes stores numeric response in "method" for responses
        has_200 = "200" in response_codes or any(
            r.get("method", "").startswith("200") for r in recs
        )
        has_cancel = "CANCEL" in all_methods
        has_bye = "BYE" in all_methods

        if has_bye and has_200:
            status = "Finished"
        elif has_200:
            status = "Answered"
        elif has_cancel:
            status = "Cancelled"
        elif all_methods == {"INVITE"} or all_methods == {"INVITE", ""}:
            status = "Trying"
        else:
            status = "Unknown"

        # Duration from min/max create_date (ms)
        timestamps = [
            r.get("create_date") or r.get("micro_ts", 0)  # already ms
            for r in recs
            if r.get("create_date") or r.get("micro_ts")
        ]
        duration_ms = (max(timestamps) - min(timestamps)) if len(timestamps) >= 2 else 0
        duration_str = _ms_to_hhmmss(duration_ms)

        # Pick representative record for detail link (first record has lowest id)
        first = sorted(recs, key=lambda r: r.get("id", 0))[0]

        rows.append(
            {
                "callid": cid,
                "from_user": invite.get("from_user") or invite.get("caller", ""),
                "to_user": invite.get("to_user") or invite.get("callee", ""),
                "src_ip": invite.get("srcIp") or invite.get("source_ip", ""),
                "dst_ip": invite.get("dstIp") or invite.get("destination_ip", ""),
                "methods": method_strs,
                "status": status,
                "create_date": first.get("create_date") or 0,
                "duration_str": duration_str,
                "id": first.get("id", 0),
            }
        )

    # Sort newest-first
    rows.sort(key=lambda r: r["create_date"], reverse=True)
    return rows


def _ms_to_hhmmss(ms: int) -> str:
    if ms <= 0:
        return "0s"
    seconds = ms // 1000
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _build_call_detail(transaction: dict) -> dict:
    """
    Parse the transaction response into template-ready structures.

    Returns a dict with keys:
        messages, flow_cols, flow_rows, session, logs,
        total_messages, first_ts_ms
    """
    data = transaction.get("data") or {}

    raw_messages: list[dict] = data.get("messages") or []
    # hosts is {"host:port": {"host": [...], "position": N}} — extract position integer
    raw_hosts: dict = data.get("hosts") or {}
    hosts_map: dict[str, int] = {
        host: (info["position"] if isinstance(info, dict) else int(info))
        for host, info in raw_hosts.items()
    }
    alias_map: dict[str, str] = data.get("alias") or {}

    # Sort by micro_ts ascending
    raw_messages.sort(key=lambda m: m.get("micro_ts", 0))

    # micro_ts on this Homer deployment is in milliseconds (13-digit epoch ms)
    first_ts = raw_messages[0].get("micro_ts", 0) if raw_messages else 0  # ms

    # Build ordered column list
    flow_cols: list[str] = [""] * max((v + 1 for v in hosts_map.values()), default=0)
    for host, idx in hosts_map.items():
        if 0 <= idx < len(flow_cols):
            flow_cols[idx] = alias_map.get(host, host)

    messages: list[dict] = []
    logs: list[dict] = []
    flow_rows: list[dict] = []

    for msg in raw_messages:
        ptype = msg.get("payloadType", 1)
        ts_ms = msg.get("micro_ts", 0)  # already in ms
        offset_ms = ts_ms - first_ts

        src_addr = f"{msg.get('srcIp', '')}:{msg.get('srcPort', '')}"
        dst_addr = f"{msg.get('dstIp', '')}:{msg.get('dstPort', '')}"

        src_col = hosts_map.get(src_addr, -1)
        dst_col = hosts_map.get(dst_addr, -1)

        method = msg.get("method") or ""
        raw_text = msg.get("raw") or ""
        create_date = msg.get("create_date") or ts_ms

        if ptype == 1:
            # SIP message
            cseq = msg.get("cseq") or ""
            user_agent = _extract_header(raw_text, "User-Agent")
            label = method or cseq
            raw_preview = raw_text[:120] if raw_text else ""
            msg_idx = len(messages)  # index into messages list for the modal

            # Extra fields for the redesigned flow diagram
            first_sip_line = ""
            if raw_text:
                for _l in raw_text.splitlines():
                    _s = _l.strip()
                    if _s:
                        first_sip_line = _s[:120]
                        break
            method_display = method
            if method and raw_text and "content-type: application/sdp" in raw_text.lower():
                method_display = f"{method} (SDP)"
            src_port = src_addr.rsplit(":", 1)[-1] if ":" in src_addr else ""
            dst_port = dst_addr.rsplit(":", 1)[-1] if ":" in dst_addr else ""
            ts_display = ""
            if ts_ms:
                try:
                    dt = datetime.fromtimestamp(ts_ms / 1000.0)
                    ts_display = dt.strftime("%m/%d/%Y %H:%M:%S.") + f"{ts_ms % 1000:03d}"
                except Exception:
                    pass
            msg_id_str = f"[{msg.get('id')}]" if msg.get("id") is not None else ""

            messages.append(
                {
                    "id": msg.get("id"),
                    "offset_ms": offset_ms,
                    "src_addr": src_addr,
                    "dst_addr": dst_addr,
                    "method": method,
                    "cseq": cseq,
                    "user_agent": user_agent,
                    "raw": raw_text,
                    "create_date": create_date,
                    "ts_ms": ts_ms,
                }
            )

            flow_rows.append(
                {
                    "src_col": src_col,
                    "dst_col": dst_col,
                    "label": label,
                    "type": "sip",
                    "method": method,
                    "method_display": method_display,
                    "offset_ms": offset_ms,
                    "raw_preview": raw_preview,
                    "msg_idx": msg_idx,
                    "src_port": src_port,
                    "dst_port": dst_port,
                    "first_sip_line": first_sip_line,
                    "ts_display": ts_display,
                    "msg_id_str": msg_id_str,
                }
            )
        elif ptype == 100:
            # HEP-LOG entry
            log_label = raw_text[:80] if raw_text else "LOG"
            logs.append(
                {
                    "ts_ms": ts_ms,
                    "src_addr": src_addr,
                    "raw": raw_text,
                    "create_date": create_date,
                }
            )
            flow_rows.append(
                {
                    "src_col": dst_col,
                    "dst_col": dst_col,
                    "label": log_label,
                    "type": "log",
                    "method": "",
                    "offset_ms": offset_ms,
                    "raw_preview": raw_text[:120],
                }
            )

    # Build session info
    session = _build_session(messages, raw_messages, data)

    return {
        "messages": messages,
        "flow_cols": flow_cols,
        "flow_rows": flow_rows,
        "session": session,
        "logs": logs,
        "total_messages": len(messages),
        "first_ts_ms": first_ts,
    }


def _extract_header(raw: str, header: str) -> str:
    """Extract the value of a SIP header from raw SIP text."""
    lower_header = header.lower() + ":"
    for line in raw.splitlines():
        if line.lower().startswith(lower_header):
            return line[len(header) + 1:].strip()
    return ""


def _build_session(
    messages: list[dict], raw_messages: list[dict], data: dict
) -> dict:
    """Derive session summary metrics from message list."""
    callid = ""
    from_user = ""
    to_user = ""
    ruri = ""
    src_addr = ""
    dst_addr = ""
    status = "Unknown"

    invite_msg = next((m for m in messages if m.get("method") == "INVITE"), None)
    if invite_msg:
        callid = next(
            (r.get("callid", "") for r in raw_messages if r.get("method") == "INVITE"), ""
        )
        from_user = next(
            (r.get("from_user", "") for r in raw_messages if r.get("method") == "INVITE"), ""
        )
        to_user = next(
            (r.get("to_user", "") for r in raw_messages if r.get("method") == "INVITE"), ""
        )
        ruri_user = next(
            (r.get("ruri_user", "") for r in raw_messages if r.get("method") == "INVITE"), ""
        )
        ruri_domain = next(
            (r.get("ruri_domain", "") for r in raw_messages if r.get("method") == "INVITE"), ""
        )
        ruri = f"{ruri_user}@{ruri_domain}" if ruri_domain else ruri_user
        src_addr = invite_msg.get("src_addr", "")
        dst_addr = invite_msg.get("dst_addr", "")

    if not callid and raw_messages:
        callid = raw_messages[0].get("callid", "")

    all_methods = {m.get("method", "") for m in messages}
    has_bye = "BYE" in all_methods

    # Timestamps (ms)
    ts_list = [m.get("ts_ms", 0) for m in messages if m.get("ts_ms")]
    first_ts = min(ts_list) if ts_list else 0
    last_ts = max(ts_list) if ts_list else 0

    # Find key events
    invite_ts = next((m["ts_ms"] for m in messages if m.get("method") == "INVITE"), first_ts)
    # 180 Ringing – look in raw payload type 1 for "180 Ringing" in status line
    ringing_ts = _find_response_ts(raw_messages, "180")
    ok_ts = _find_response_ts(raw_messages, "200")
    bye_ts = next((m["ts_ms"] for m in messages if m.get("method") == "BYE"), last_ts)

    ringing_ms = (ringing_ts - invite_ts) if ringing_ts and invite_ts else 0
    setup_ms = (ok_ts - invite_ts) if ok_ts and invite_ts else 0
    disconnect_ms = (last_ts - bye_ts) if bye_ts and last_ts else 0
    duration_ms = (bye_ts - ok_ts) if ok_ts and bye_ts else (last_ts - first_ts)

    if has_bye and ok_ts:
        status = "Finished"
    elif ok_ts:
        status = "Answered"
    elif "CANCEL" in all_methods:
        status = "Cancelled"
    else:
        status = "In Progress"

    # Method counts for doughnut chart
    method_counts: dict[str, int] = {}
    for m in messages:
        meth = m.get("method", "")
        if meth:
            method_counts[meth] = method_counts.get(meth, 0) + 1

    return {
        "callid": callid,
        "from_user": from_user,
        "to_user": to_user,
        "ruri": ruri,
        "src_addr": src_addr,
        "dst_addr": dst_addr,
        "status": status,
        "duration_str": _ms_to_hhmmss(duration_ms),
        "duration_sec": duration_ms // 1000,
        "ringing_ms": ringing_ms,
        "setup_ms": setup_ms,
        "disconnect_ms": disconnect_ms,
        "method_counts": method_counts,
    }


def _find_response_ts(raw_messages: list[dict], code: str) -> int:
    """Find the ms timestamp of the first message whose raw text starts with `SIP/2.0 {code}`."""
    for msg in raw_messages:
        raw = msg.get("raw") or ""
        if raw.startswith(f"SIP/2.0 {code}") or raw.startswith(f"SIP/2.0 {code} "):
            return msg.get("micro_ts") or 0  # already in ms
    return 0


def _call_summary_from_transaction(callid: str, transaction: dict) -> dict | None:
    """
    Build a single search-result summary row from a call/transaction response.
    Used when searching by callid only to bypass the 200-record search cap.
    """
    data = transaction.get("data") or {}
    messages: list[dict] = data.get("messages") or []
    # Only SIP messages (payloadType == 1)
    sip_msgs = [m for m in messages if m.get("payloadType", 1) == 1]
    if not sip_msgs:
        return None

    sip_msgs.sort(key=lambda m: m.get("micro_ts", 0))

    invite = next((m for m in sip_msgs if m.get("method") == "INVITE"), sip_msgs[0])
    methods = sorted({m.get("method", "") for m in sip_msgs if m.get("method")})
    all_methods = {m.get("method", "") for m in sip_msgs}

    has_200 = any(m.get("raw", "").startswith("SIP/2.0 200") for m in sip_msgs)
    has_cancel = "CANCEL" in all_methods
    has_bye = "BYE" in all_methods

    if has_bye and has_200:
        status = "Finished"
    elif has_200:
        status = "Answered"
    elif has_cancel:
        status = "Cancelled"
    elif all_methods <= {"INVITE", ""}:
        status = "Trying"
    else:
        status = "Unknown"

    timestamps = [m.get("micro_ts", 0) for m in sip_msgs if m.get("micro_ts")]
    duration_ms = (max(timestamps) - min(timestamps)) if len(timestamps) >= 2 else 0

    return {
        "callid": callid,
        "from_user": invite.get("from_user", ""),
        "to_user": invite.get("to_user", ""),
        "src_ip": invite.get("srcIp", ""),
        "dst_ip": invite.get("dstIp", ""),
        "methods": methods,
        "status": status,
        "create_date": sip_msgs[0].get("micro_ts", 0),
        "duration_str": _ms_to_hhmmss(duration_ms),
        "id": sip_msgs[0].get("id", 0),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/homer", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def homer_index(
    request: Request,
    callid: Optional[str] = None,
    from_user: Optional[str] = None,
    to_user: Optional[str] = None,
    method: Optional[str] = None,
    src_ip: Optional[str] = None,
    dst_ip: Optional[str] = None,
    from_tag: Optional[str] = None,
    to_tag: Optional[str] = None,
    hours: int = 168,
    search: Optional[str] = None,  # present when the form was submitted
):
    """Homer SIP search page."""
    if not _HOMER_ENABLED():
        return RedirectResponse(url="/", status_code=303)

    current_user = get_current_user(request)
    error: Optional[str] = None
    calls: list[dict] = []
    latency_ms: float = 0.0
    searched = False

    filters = {
        "callid": callid or "",
        "from_user": from_user or "",
        "to_user": to_user or "",
        "method": method or "",
        "source_ip": src_ip or "",
        "dst_ip": dst_ip or "",
        "from_tag": from_tag or "",
        "to_tag": to_tag or "",
    }

    # Fetch whenever the search form was submitted (search param present),
    # even if all filter fields are empty (returns all recent calls).
    if search is not None:
        searched = True
        try:
            hc: HomerClient = await get_homer_client()
            now_ms = int(time.time() * 1000)

            # When the only active filter is callid, Homer's search endpoint may miss
            # older calls because it caps results at 200 most-recent records.
            # The transaction endpoint supports callid filtering without the cap,
            # so we use it directly with a 30-day window.
            other_filters = [
                filters[k]
                for k in ("from_user", "to_user", "method", "source_ip", "dst_ip", "from_tag", "to_tag")
            ]
            callid_only = bool(filters["callid"]) and not any(other_filters)

            if callid_only:
                _THIRTY_DAYS_MS = 30 * 24 * 3_600_000
                transaction, latency_ms = await hc.get_call_transaction(
                    filters["callid"], 0, now_ms, window_ms=_THIRTY_DAYS_MS
                )
                summary = _call_summary_from_transaction(filters["callid"], transaction)
                calls = [summary] if summary else []
            else:
                time_from_ms = now_ms - hours * 3_600_000
                records, latency_ms = await hc.search_calls(filters, time_from_ms, now_ms)
                calls = _group_calls(records)
        except Exception as exc:
            error = str(exc)

    return request.app.state.templates.TemplateResponse(
        "homer/index.html.j2",
        {
            "request": request,
            "current_user": current_user,
            "csrf_token": get_csrf_token(request),
            "filters": filters,
            "hours": hours,
            "calls": calls,
            "latency_ms": round(latency_ms, 1),
            "searched": searched,
            "error": error,
        },
    )


@router.get(
    "/homer/call/{callid}", response_class=HTMLResponse, dependencies=[Depends(requires_admin)]
)
async def homer_call_detail(
    request: Request,
    callid: str,
    id: Optional[int] = None,
    ts: Optional[int] = None,
    tab: str = "flow",
):
    """Homer call detail page with 5 tabs."""
    if not _HOMER_ENABLED():
        return RedirectResponse(url="/", status_code=303)

    current_user = get_current_user(request)
    error: Optional[str] = None
    detail: dict = {}
    latency_ms: float = 0.0

    try:
        hc: HomerClient = await get_homer_client()
        ts_ms = ts or int(time.time() * 1000)
        transaction, latency_ms = await hc.get_call_transaction(callid, id or 0, ts_ms)
        detail = _build_call_detail(transaction)
    except Exception as exc:
        error = str(exc)

    return request.app.state.templates.TemplateResponse(
        "homer/call.html.j2",
        {
            "request": request,
            "current_user": current_user,
            "csrf_token": get_csrf_token(request),
            "callid": callid,
            "record_id": id,
            "ts": ts,
            "tab": tab,
            "latency_ms": round(latency_ms, 1),
            "error": error,
            **detail,
        },
    )


@router.get(
    "/homer/call/{callid}/export.json",
    dependencies=[Depends(requires_admin)],
)
async def homer_call_export(
    request: Request,
    callid: str,
    id: Optional[int] = None,
    ts: Optional[int] = None,
):
    """Download raw transaction JSON for a call."""
    if not _HOMER_ENABLED():
        return RedirectResponse(url="/", status_code=303)

    try:
        hc: HomerClient = await get_homer_client()
        ts_ms = ts or int(time.time() * 1000)
        transaction, _ = await hc.get_call_transaction(callid, id or 0, ts_ms)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    safe_callid = "".join(c if c.isalnum() or c in "-_." else "_" for c in callid)
    return JSONResponse(
        content=transaction,
        headers={
            "Content-Disposition": f'attachment; filename="call-{safe_callid}.json"',
        },
    )
