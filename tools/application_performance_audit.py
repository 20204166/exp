"""Report application performance metrics captured by Diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def report_payload(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Project observer metrics without recalculating or extending their meaning."""

    observability = diagnostics.get("observability") or {}
    metrics = observability.get("metrics") or []
    return {
        "captured_at": observability.get("captured_at"),
        "metrics": [
            {
                key: metric[key]
                for key in (
                    "target",
                    "count",
                    "successes",
                    "failures",
                    "cancellations",
                    "in_flight",
                    "peak_in_flight",
                    "distribution",
                )
                if key in metric
            }
            for metric in metrics
            if isinstance(metric, dict)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = report_payload(json.loads(args.diagnostics.read_text(encoding="utf-8")))
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
