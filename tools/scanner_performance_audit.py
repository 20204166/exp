"""Run the read-only scanner performance baseline and write evidence reports."""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
from pathlib import Path
from typing import Any, cast

from maintenance.components.coordinator import AppCoordinator
from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.components.temperature import TemperatureTelemetry
from maintenance.performance_audit import (
    AuditRunner,
    CandidateFinding,
    Evidence,
    FindingStatus,
    MeasurementRecord,
    MeasurementState,
    OperationTiming,
    ResourceCounters,
    default_workloads,
    deterministic_coordination_metrics,
    report_payload,
    summarize_samples,
)
from maintenance.scanner import SystemScanner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/performance"))
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument(
        "--platform-mode",
        choices=("native", "simulated-windows", "simulated-macos"),
        default="native",
    )
    parser.add_argument("--include-memory", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser


def _native_operation(scanner: SystemScanner, key: str) -> Any:
    if key == "dashboard":
        return scanner.scan_dashboard
    if key.startswith("component:"):
        component = key.split(":", 1)[1]
        return lambda: scanner.scan_component(component)
    if key == "gpu-telemetry":
        return scanner.gpu_details
    if key == "temperature-telemetry":
        telemetry = TemperatureTelemetry()
        return lambda: telemetry.render_state(("cpu", "gpu", "storage", "battery"))
    if key == "downloads":
        return scanner.scan_downloads
    if key == "processes":
        return scanner.scan_processes
    if key in ("background-delivery", "app-coordinator"):
        coordinator = AppCoordinator(
            runner=lambda worker: worker(),
            deliver=lambda callback: callback(),
        )

        def run_coordinated() -> int | None:
            return coordinator.run(
                key,
                lambda cancel_event, _progress: scanner.scan_component(
                    "memory", cancel_event
                ),
            )

        return run_coordinated
    if key == "network-discovery":

        class Backend:
            available = True

            def start(self, _advertisement: Any) -> None:
                return None

            def stop(self) -> None:
                return None

        discovery = NetworkDiscovery(
            "audit-local",
            advertisement=DiscoveryAdvertisement(
                stable_id="audit-local",
                display_name="Audit Local",
                hostname="localhost",
                app_version="audit",
            ),
            backend_factory=cast(Any, lambda _listener: Backend()),
        )

        def run_discovery() -> None:
            discovery.start()
            discovery.expire_stale()

        return run_discovery
    return None


def _simulated_operation(key: str) -> Any:
    """Return a deterministic adapter for unavailable platform branches."""

    return lambda: {"platform": key, "status": "simulated", "items": 3}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Scanner Performance Baseline",
        "",
        "| Workload | Scenario | Median | P95 | Evidence |",
        "|---|---|---:|---:|---|",
    ]
    for record in payload["records"]:
        data = record
        samples = tuple(float(value) for value in data["samples"])
        summary = summarize_samples(samples) if samples else {"median": 0.0, "p95": 0.0}
        lines.append(
            f"| {data['workload']} | {data['scenario']} | {summary['median']:.6f}s | {summary['p95']:.6f}s | {data['evidence']} |"
        )
    lines.extend(("", "## Findings", ""))
    for finding in payload["findings"]:
        lines.append(
            f"- `{finding['status']}`: {finding['workload']} - {finding['rationale']}"
        )
    coordination = payload.get("coordination_metrics")
    if coordination is not None:
        data = cast(dict[str, Any], coordination)
        lines.extend(
            (
                "",
                "## Coordination Metrics",
                "",
                f"- Evidence: `{data['evidence']}` on `{data['platform']}`",
                f"- Provenance: {data['provenance']}",
                f"- Callback deliveries: {data['callback_delivery_count']}",
                f"- Duplicate task starts: {data['duplicate_task_starts']}",
                f"- Hidden-work starts: {data['hidden_work_starts']}",
                f"- Visible refresh latency: {data['visible_refresh_latency_seconds']:.3f}s",
                f"- Discovery burst renders: {data['burst_render_count']}",
                f"- Events versus rendered updates: {data['event_count']} versus {data['rendered_update_count']}",
            )
        )
    return "\n".join(lines) + "\n"


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions <= 0:
        raise ValueError("repetitions must be positive")
    evidence = cast(
        Evidence, "native" if args.platform_mode == "native" else "simulated"
    )
    platform_name = platform.platform() if evidence == "native" else args.platform_mode
    records: list[MeasurementRecord] = []
    for workload in default_workloads():
        scanner = SystemScanner(Path.home() / "Downloads")
        operation = (
            _native_operation(scanner, workload.key)
            if evidence == "native"
            else _simulated_operation(workload.key)
        )
        if operation is None:
            records.append(
                MeasurementRecord(
                    workload=workload.key,
                    scenario="unavailable",
                    platform=platform_name,
                    evidence="unavailable",
                    state="warm",
                    samples=(),
                    resources=ResourceCounters(),
                    error_classification="unavailable path",
                )
            )
            continue
        runner = AuditRunner(include_memory=args.include_memory)
        cold = runner.measure(operation)
        warm = tuple(runner.measure(operation) for _ in range(args.repetitions))
        states: tuple[tuple[MeasurementState, tuple[OperationTiming, ...]], ...] = (
            ("cold", (cold,)),
            ("warm", warm),
        )
        for state, timings in states:
            records.append(
                MeasurementRecord(
                    workload=workload.key,
                    scenario=state,
                    platform=platform_name,
                    evidence=evidence,
                    state=state,
                    samples=tuple(timing.total_seconds for timing in timings),
                    resources=ResourceCounters(
                        cpu_seconds=sum(timing.cpu_seconds for timing in timings),
                        peak_memory_bytes=max(
                            (timing.peak_memory_bytes or 0 for timing in timings),
                            default=0,
                        ),
                    ),
                    scanner_seconds=tuple(timing.scanner_seconds for timing in timings),
                    coordinator_seconds=tuple(
                        timing.coordinator_seconds for timing in timings
                    ),
                )
            )
    findings = tuple(_finding_for(record) for record in records)
    return report_payload(
        tuple(records),
        findings,
        deterministic_coordination_metrics(
            platform=platform_name,
            evidence=evidence,
        ),
    )


def _finding_for(record: MeasurementRecord) -> CandidateFinding:
    status: FindingStatus
    if record.scenario == "unavailable":
        status = "not actionable"
        rationale = "This platform path is unavailable in the current runtime."
    elif record.workload == "processes":
        status = "not actionable"
        rationale = "The dominant cost is the intentional CPU sampling interval; accuracy needs an explicit product decision."
    elif record.workload in {"dashboard", "component:cpu"} and record.state == "cold":
        status = "not actionable"
        rationale = "The cold cost is initial CPU sampling; warm scans are the relevant refresh path."
    elif record.workload == "downloads":
        status = "requires design"
        rationale = "Downloads remains a measured hotspot; hashing and metadata costs need separate cross-platform evidence."
    else:
        status = "noise"
        rationale = "No actionable hotspot is established by this baseline alone."
    return CandidateFinding(
        workload=record.workload,
        candidate="baseline observation",
        status=status,
        rationale=rationale,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = run_audit(args)
    output_dir: Path = args.output_dir
    _atomic_write(
        output_dir / "scanner-performance.json", json.dumps(payload, indent=2)
    )
    _atomic_write(output_dir / "scanner-performance.md", _markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
