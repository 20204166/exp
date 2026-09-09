"""Tests for the scanner performance audit measurement models."""

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

from maintenance.performance_audit import (
    AuditRunner,
    CandidateFinding,
    CoordinationMetrics,
    MeasurementRecord,
    ResourceCounters,
    WorkloadSpec,
    default_workloads,
    deterministic_coordination_metrics,
    interleave_modes,
    report_payload,
    summarize_samples,
)
from tests.support.performance_audit import (
    EMPTY_PROFILE,
    LARGE_PROFILE,
    NATIVE_PLATFORM,
    SIMULATED_PLATFORM,
    TYPICAL_PROFILE,
    UNAVAILABLE_PLATFORM,
    FailureKind,
    classify_result,
    make_performance_fixtures,
)
from tools.scanner_performance_audit import main as audit_main


class PerformanceAuditModelTests(unittest.TestCase):
    def test_models_are_immutable_and_slotted(self) -> None:
        workload = WorkloadSpec("dashboard", ("cold", "warm"))

        with self.assertRaises(FrozenInstanceError):
            workload.key = "other"  # type: ignore[misc]
        self.assertFalse(hasattr(workload, "__dict__"))

    def test_serialization_preserves_measurement_evidence(self) -> None:
        record = MeasurementRecord(
            workload="dashboard-refresh",
            scenario="warm",
            platform="Linux-x86_64",
            evidence="native",
            state="warm",
            samples=(0.012, 0.015),
            resources=ResourceCounters(
                cpu_seconds=0.008,
                peak_memory_bytes=2048,
                allocations=7,
                io_read_bytes=128,
                io_write_bytes=64,
            ),
            error_classification=None,
            scanner_seconds=(0.010, 0.012),
            coordinator_seconds=(0.002, 0.003),
        )

        payload = record.to_dict()
        self.assertEqual(json.loads(json.dumps(payload)), payload)
        self.assertEqual(payload["workload"], "dashboard-refresh")
        self.assertEqual(payload["scenario"], "warm")
        self.assertEqual(payload["evidence"], "native")
        self.assertEqual(payload["state"], "warm")
        self.assertEqual(payload["samples"], [0.012, 0.015])
        self.assertEqual(payload["resources"]["allocations"], 7)  # type: ignore[index]
        self.assertEqual(payload["scanner_seconds"], [0.010, 0.012])
        self.assertEqual(payload["coordinator_seconds"], [0.002, 0.003])

    def test_all_models_emit_json_compatible_primitives(self) -> None:
        values = (
            WorkloadSpec("network", ("failure",), "network scan"),
            ResourceCounters(),
            CandidateFinding(
                "network", "repeated discovery", "noise", "no stable delta"
            ),
            CoordinationMetrics("Linux-x86_64", "simulated", 1, 0, 0, 0.125, 1, 5, 1),
        )

        for value in values:
            payload = value.to_dict()
            self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_missing_required_scenario_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            WorkloadSpec("dashboard", ())
        with self.assertRaises(ValueError):
            MeasurementRecord(
                workload="dashboard",
                scenario="",
                platform="Linux",
                evidence="simulated",
                state="cold",
                samples=(),
                resources=ResourceCounters(),
            )

    def test_sample_summary_reports_percentiles_and_outliers(self) -> None:
        summary = summarize_samples((1.0, 2.0, 3.0, 4.0, 100.0))

        self.assertEqual(summary["median"], 3.0)
        self.assertEqual(summary["p25"], 2.0)
        self.assertEqual(summary["p75"], 4.0)
        self.assertAlmostEqual(summary["p95"], 80.8)
        self.assertEqual(summary["outliers"], 1)

    def test_interleave_modes_alternates_baseline_and_candidate(self) -> None:
        self.assertEqual(
            tuple(interleave_modes(("baseline", "candidate"), 3)),
            ("baseline", "candidate", "baseline", "candidate", "baseline", "candidate"),
        )

    def test_runner_separates_total_scanner_and_coordinator_time(self) -> None:
        runner = AuditRunner(clock=iter((1.0, 1.4)).__next__)

        result = runner.measure(
            lambda: "snapshot",
            split_timing=lambda _result: (0.3, 0.1),
        )

        self.assertEqual(result.value, "snapshot")
        self.assertAlmostEqual(result.total_seconds, 0.4)
        self.assertAlmostEqual(result.scanner_seconds, 0.3)
        self.assertAlmostEqual(result.coordinator_seconds, 0.1)

    def test_single_sample_summary_is_supported(self) -> None:
        self.assertEqual(summarize_samples((0.25,))["p95"], 0.25)

    def test_workload_matrix_contains_all_catalog_components(self) -> None:
        keys = {workload.key for workload in default_workloads()}

        self.assertIn("dashboard", keys)
        for key in ("cpu", "memory", "storage", "gpu", "network", "battery"):
            self.assertIn(f"component:{key}", keys)

    def test_report_payload_contains_records_findings_and_workloads(self) -> None:
        record = MeasurementRecord(
            workload="dashboard",
            scenario="warm",
            platform="Linux",
            evidence="native",
            state="warm",
            samples=(0.1,),
            resources=ResourceCounters(),
        )
        payload = report_payload((record,), ())

        self.assertEqual(len(payload["records"]), 1)  # type: ignore[arg-type]
        self.assertEqual(payload["findings"], [])
        self.assertTrue(payload["workloads"])  # type: ignore[truthy-bool]

    def test_coordination_metrics_distinguish_events_from_rendered_updates(
        self,
    ) -> None:
        metrics = deterministic_coordination_metrics(
            platform="Windows-x86_64", evidence="simulated"
        )

        self.assertEqual(metrics.callback_delivery_count, 1)
        self.assertEqual(metrics.duplicate_task_starts, 0)
        self.assertEqual(metrics.hidden_work_starts, 0)
        self.assertEqual(metrics.visible_refresh_latency_seconds, 0.125)
        self.assertEqual(metrics.burst_render_count, 1)
        self.assertEqual(metrics.event_count, 5)
        self.assertEqual(metrics.rendered_update_count, 1)
        self.assertEqual(metrics.to_dict()["evidence"], "simulated")
        self.assertIn(
            "does not measure a native path", str(metrics.to_dict()["provenance"])
        )

    def test_deterministic_coordination_metrics_cannot_claim_native_evidence(
        self,
    ) -> None:
        metrics = deterministic_coordination_metrics(
            platform="Linux-x86_64", evidence="native"
        )

        self.assertEqual(metrics.evidence, "simulated")
        self.assertIn("fixed", metrics.provenance.lower())

    def test_cli_writes_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                audit_main(
                    [
                        "--output-dir",
                        directory,
                        "--repetitions",
                        "1",
                        "--platform-mode",
                        "simulated-windows",
                    ]
                ),
                0,
            )
            self.assertTrue(Path(directory, "scanner-performance.json").is_file())
            self.assertTrue(Path(directory, "scanner-performance.md").is_file())
            report = json.loads(
                Path(directory, "scanner-performance.json").read_text(encoding="utf-8")
            )
            coordination = report["coordination_metrics"]
            self.assertEqual(coordination["evidence"], "simulated")
            self.assertEqual(coordination["event_count"], 5)
            self.assertEqual(coordination["rendered_update_count"], 1)
            self.assertEqual(
                coordination["provenance"],
                "Fixed deterministic queue/render fixture; does not measure a native path.",
            )
            self.assertIn(
                "Coordination Metrics",
                Path(directory, "scanner-performance.md").read_text(encoding="utf-8"),
            )


class PerformanceAuditFixtureTests(unittest.TestCase):
    def test_profiles_and_platform_evidence_are_fixed(self) -> None:
        self.assertEqual(EMPTY_PROFILE.size, 0)
        self.assertEqual(TYPICAL_PROFILE.size, 3)
        self.assertEqual(LARGE_PROFILE.size, 1000)
        self.assertEqual(NATIVE_PLATFORM.evidence, "native")
        self.assertEqual(SIMULATED_PLATFORM.evidence, "simulated")
        self.assertFalse(UNAVAILABLE_PLATFORM.available)

    def test_factory_state_is_fresh_and_cache_is_counted(self) -> None:
        scanner, _coordinator, counters = make_performance_fixtures()
        self.assertEqual(scanner.scan()["status"], "ok")
        self.assertEqual(scanner.scan(use_cache=True)["status"], "ok")
        self.assertEqual(counters.cache_hits, 1)
        other, _other_coordinator, other_counters = make_performance_fixtures()
        self.assertIsNot(scanner, other)
        self.assertEqual(other_counters.cache_hits, 0)

    def test_failure_outcomes_keep_the_result_contract(self) -> None:
        for failure in (
            "missing dependency",
            "permission failure",
            "subprocess failure",
            "timeout",
        ):
            with self.subTest(failure=failure):
                scanner, _coordinator, _counters = make_performance_fixtures(
                    failure=cast(
                        FailureKind,
                        failure,
                    )
                )
                result = scanner.scan()
                self.assertEqual(classify_result(result), failure)
                self.assertEqual(
                    set(result),
                    {
                        "status",
                        "profile",
                        "items",
                        "count",
                        "error_classification",
                    },
                )

    def test_cancellation_is_cooperative_and_counted(self) -> None:
        scanner, coordinator, counters = make_performance_fixtures()
        generation = coordinator.run("scan", scanner.scan)
        self.assertIsNotNone(generation)
        coordinator.cancel("scan")
        self.assertEqual(counters.cancellation_calls, 1)
        coordinator.run_worker()
        coordinator.deliver()
        self.assertFalse(coordinator.in_flight("scan"))

    def test_coalescing_runs_one_rerun(self) -> None:
        scanner, coordinator, counters = make_performance_fixtures()
        self.assertIsNotNone(coordinator.run("scan", scanner.scan))
        self.assertIsNone(coordinator.run("scan", scanner.scan))
        coordinator.run_worker()
        coordinator.deliver()
        self.assertEqual(counters.runs, 2)
        self.assertEqual(counters.retries, 1)
        self.assertEqual(len(coordinator.workers), 1)

    def test_stale_generation_is_not_delivered(self) -> None:
        scanner, coordinator, counters = make_performance_fixtures()
        first = coordinator.run("scan", scanner.scan)
        if first is None:
            self.fail("first generation did not start")
        self.assertTrue(coordinator.finish("scan", first, {"old": True}))
        second = coordinator.run("scan", scanner.scan)
        if second is None:
            self.fail("replacement generation did not start")
        self.assertFalse(coordinator.finish("scan", first, {"late": True}))
        self.assertGreater(second, first)
        self.assertEqual(counters.deliveries, 0)

    def test_post_shutdown_delivery_is_recorded_as_late(self) -> None:
        scanner, coordinator, counters = make_performance_fixtures()
        coordinator.run("scan", scanner.scan)
        coordinator.run_worker()
        coordinator.shutdown()
        coordinator.deliver()
        self.assertEqual(counters.late_results, 1)

    def test_optional_dependency_probe_is_counted(self) -> None:
        scanner, _coordinator, counters = make_performance_fixtures()
        self.assertFalse(scanner.probe_optional_dependency(False))
        self.assertEqual(counters.probe_calls, 1)


if __name__ == "__main__":
    unittest.main()
