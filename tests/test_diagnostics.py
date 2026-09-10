"""Bounded diagnostics snapshot tests."""

import json
import unittest
from types import SimpleNamespace

from maintenance.diagnostics import (
    MAX_DETAIL_LENGTH,
    build_diagnostics_snapshot,
    format_timestamp,
    serialize_diagnostics,
    truncate_detail,
)


class DiagnosticsSnapshotTests(unittest.TestCase):
    def test_format_timestamp_is_human_readable(self) -> None:
        self.assertRegex(format_timestamp(1789056712.440), r"^\d{2}:\d{2}:\d{2}$")
        self.assertEqual(format_timestamp(None), "No data yet")

    def test_snapshot_projects_current_state_without_secrets(self) -> None:
        scheduler = SimpleNamespace(
            intervals={"cpu": 1000},
            diagnostic_state=lambda _key: (
                False,
                False,
                12.5,
                ("execution_failed", "bad"),
            ),
        )
        coordinator = SimpleNamespace(
            diagnostic_states=lambda: (
                (
                    "component:cpu",
                    SimpleNamespace(
                        generation=3,
                        in_flight=True,
                        last_result=None,
                        last_success=None,
                        last_error=None,
                    ),
                ),
            )
        )
        registry = SimpleNamespace(contexts=lambda: ())
        ui = SimpleNamespace(
            pending_count=1,
            render_requests=2,
            render_commits=1,
            coalesced_requests=0,
            stale_rejections=4,
        )

        snapshot = build_diagnostics_snapshot(
            scheduler=scheduler,
            coordinator=coordinator,
            registry=registry,
            ui_coordinator=ui,
            capabilities={"cpu": "supported"},
        )

        self.assertEqual(snapshot.components[0].last_success, 12.5)
        self.assertTrue(snapshot.operations[0].in_flight)
        self.assertEqual(snapshot.render.stale_rejections, 4)
        self.assertNotIn("secret", serialize_diagnostics(snapshot))

    def test_detail_is_bounded(self) -> None:
        detail = truncate_detail("x" * (MAX_DETAIL_LENGTH + 20))
        self.assertEqual(len(detail or ""), MAX_DETAIL_LENGTH)

    def test_serializer_is_json_safe(self) -> None:
        scheduler = SimpleNamespace(intervals={}, diagnostic_state=lambda _key: ())
        coordinator = SimpleNamespace(diagnostic_states=lambda: ())
        registry = SimpleNamespace(contexts=lambda: ())
        ui = SimpleNamespace(
            pending_count=0,
            render_requests=0,
            render_commits=0,
            coalesced_requests=0,
            stale_rejections=0,
        )
        payload = serialize_diagnostics(
            build_diagnostics_snapshot(
                scheduler=scheduler,
                coordinator=coordinator,
                registry=registry,
                ui_coordinator=ui,
            )
        )
        self.assertIsInstance(json.loads(payload), dict)


if __name__ == "__main__":
    unittest.main()
