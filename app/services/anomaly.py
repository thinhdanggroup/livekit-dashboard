"""Lightweight anomaly detection heuristics for the dashboard overview.

Each heuristic inspects DashboardStats fields and returns an Observation
when something looks unusual. These are informational — not alerts — and
are displayed on the overview page as contextual hints to the operator.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Observation:
    severity: str        # "info" | "warning" | "critical"
    title: str
    detail: str
    icon: str = "bi-exclamation-circle"


def detect(stats) -> list[Observation]:
    """Run all heuristics against *stats* and return a list of Observations.

    Returns an empty list when stats has an error or everything looks normal.
    """
    if getattr(stats, "error", None):
        return []

    obs: list[Observation] = []

    latency = getattr(stats, "api_latency_ms", 0) or 0
    if latency > 500:
        obs.append(Observation(
            severity="critical",
            title="Very high API latency",
            detail=f"LiveKit API responded in {latency:.0f} ms — network or server may be under load.",
            icon="bi-speedometer",
        ))
    elif latency > 200:
        obs.append(Observation(
            severity="warning",
            title="Elevated API latency",
            detail=f"LiveKit API responded in {latency:.0f} ms — watch for participant connection issues.",
            icon="bi-speedometer",
        ))

    rooms_total = getattr(stats, "rooms_total", 0) or 0
    rooms_active = getattr(stats, "rooms_active", 0) or 0
    if rooms_total > 0 and rooms_active == 0:
        obs.append(Observation(
            severity="info",
            title="All rooms are empty",
            detail=f"{rooms_total} room{'s' if rooms_total != 1 else ''} exist but none have participants.",
            icon="bi-door-open",
        ))

    participants_total = getattr(stats, "participants_total", 0) or 0
    if rooms_active > 0 and participants_total > 0:
        avg = participants_total / rooms_active
        if avg > 100:
            obs.append(Observation(
                severity="warning",
                title="High average participant count",
                detail=f"Average {avg:.0f} participants per active room — check capacity limits.",
                icon="bi-people",
            ))

    egress_active = getattr(stats, "egress_active", 0) or 0
    if egress_active > 20:
        obs.append(Observation(
            severity="warning",
            title="Many concurrent egress jobs",
            detail=f"{egress_active} active egress jobs — monitor for server resource pressure.",
            icon="bi-record-circle",
        ))

    ingress_active = getattr(stats, "ingress_active", 0) or 0
    sip_trunks = getattr(stats, "sip_trunks", 0) or 0
    if ingress_active == 0 and egress_active == 0 and rooms_active > 5:
        obs.append(Observation(
            severity="info",
            title="No recording or streaming active",
            detail=f"{rooms_active} active rooms but no egress or ingress jobs running.",
            icon="bi-camera-video-off",
        ))

    return obs
