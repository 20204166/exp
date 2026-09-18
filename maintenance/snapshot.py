"""Read-only snapshot command for the installed System Analyzer project.

Reuses the existing ``algo.Analyzer`` facade (which delegates to
``SystemScanner``) so the CLI never duplicates scanner code. It performs a
dashboard scan and prints the result as JSON; it never opens a window, never
quits processes, and never moves files.
"""

import argparse
import json
import sys
from typing import Any

from maintenance.models import resource_status


def _temperature_payload(sample: Any) -> dict[str, Any]:
    """Serialize one TemperatureSample to a JSON-safe dict.

    ``sampled_monotonic`` is a process-relative clock value and is omitted;
    ``sampled_at`` (an aware datetime) is sufficient for external consumers.
    """

    return {
        "component": sample.component,
        "sensor_id": sample.sensor_id,
        "sensor_name": sample.sensor_name,
        "value_celsius": sample.value_celsius,
        "sampled_at": sample.sampled_at.isoformat(),
    }


def _snapshot_payload(snapshot: Any) -> dict[str, Any]:
    """Convert one dashboard snapshot into a JSON-safe payload.

    Each resource entry includes:
    - ``status``: the canonical single-line health label from
      :func:`~maintenance.models.resource_status` (``None`` when the
      resource is fully supported); consumers should prefer this over
      reconstructing the same logic from ``failed`` + ``capability``.
    - ``temperatures``: zero or more sensor readings for resources that
      carry live temperature data (e.g. CPU thermals); empty list when none.
    - ``temperature_unavailable_reason``: non-``None`` when temperature
      collection was attempted but failed for a known reason.
    """

    return {
        "system_label": snapshot.system_label,
        "scanned_at": snapshot.scanned_at.isoformat(),
        "resources": [
            {
                "key": resource.key,
                "title": resource.title,
                "value": resource.value,
                "status": resource_status(resource),
                "subtitle": resource.subtitle,
                "percent": resource.percent,
                "actionable": resource.actionable,
                "failed": resource.failed,
                "capability": resource.capability.value,
                "details": list(resource.details),
                "temperatures": [
                    _temperature_payload(t) for t in resource.temperatures
                ],
                "temperature_unavailable_reason": resource.temperature_unavailable_reason,
            }
            for resource in snapshot.resources
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Run one read-only dashboard scan and print it as JSON."""

    parser = argparse.ArgumentParser(
        prog="system-analyzer-snapshot",
        description=(
            "Print a read-only snapshot of the current system as JSON. "
            "Nothing is changed, stopped, or moved."
        ),
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON (single line) instead of indented output",
    )
    args = parser.parse_args(argv)

    try:
        from algo import Analyzer
    except ImportError as error:
        print(
            f"system-analyzer-snapshot: cannot load the app: {error}", file=sys.stderr
        )
        return 1

    snapshot = Analyzer().dashboard_snapshot()
    payload = _snapshot_payload(snapshot)
    print(json.dumps(payload, indent=None if args.compact else 2))
    return 0
