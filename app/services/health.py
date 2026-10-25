"""Plain-English health summary for the dashboard overview.

Turns DashboardStats into a single severity, a headline, and a few detail
lines an operator can read at a glance.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.dashboard import DashboardStats

# Mirror the thresholds in app/services/anomaly.py so the overview never
# disagrees with the anomaly observations shown alongside it.
_CRITICAL_LATENCY_MS = 500  # anomaly.py: latency > 500 is "critical"
_WARNING_LATENCY_MS = 200   # anomaly.py: latency > 200 is "warning"


@dataclass
class HealthSummary:
    severity: str   # "down" | "degraded" | "healthy"
    headline: str
    details: list[str]


def evaluate(stats: DashboardStats) -> HealthSummary:
    """Summarise *stats* as a severity, headline and detail lines."""
    details = _details(stats)

    if stats.error:
        return HealthSummary(
            severity="down",
            headline=f"LiveKit API unreachable: {stats.error}",
            details=details,
        )

    latency = stats.api_latency_ms
    if latency > _CRITICAL_LATENCY_MS:
        severity = "down"
        headline = f"LiveKit API very slow: {latency:.0f} ms"
    elif latency > _WARNING_LATENCY_MS:
        severity = "degraded"
        headline = f"LiveKit API slow: {latency:.0f} ms"
    else:
        severity = "healthy"
        headline = f"LiveKit API healthy: {latency:.0f} ms"

    return HealthSummary(severity=severity, headline=headline, details=details)


def _details(stats: DashboardStats) -> list[str]:
    details = [
        f"{stats.rooms_active} of {stats.rooms_total} rooms active",
        f"{stats.participants_total} participants connected",
        f"{stats.egress_active} egress jobs running",
        f"{stats.ingress_active} ingress jobs running",
    ]
    if stats.sip_enabled:
        details.append(f"{stats.sip_trunks} SIP trunks")
    return details
