"""Regression coverage for per-node thermal telemetry isolation."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from maintenance.components.temperature import TemperatureSample
from maintenance.models import CapabilityState
from maintenance.nodes import NodeRegistry
from maintenance.ui.window_components import thermal_render_state
from tests.support.models import make_summary
from tests.support.nodes import make_local_context, make_remote_context
from tests.support.window import make_window as make_bare_window


class ThermalNodeIsolationTests(unittest.TestCase):
    def test_switching_selected_node_does_not_leak_thermal_history(self) -> None:
        window = make_bare_window()
        registry = NodeRegistry()
        local_ctx = make_local_context()
        remote_ctx = make_remote_context("peer-a")
        registry.register_context(local_ctx)
        registry.register_context(remote_ctx)
        registry.select(local_ctx.node_id)
        window._node_registry = registry
        window._selected_node_id = registry.selected_id()

        sample = TemperatureSample(
            component="cpu",
            sensor_id="cpu0",
            sensor_name="cpu0",
            value_celsius=55.0,
            sampled_at=datetime.now(timezone.utc),
            sampled_monotonic=0.0,
        )
        local_ctx.telemetry.record_summary(
            "cpu",
            make_summary(
                "cpu",
                "CPU",
                capability=CapabilityState.SUPPORTED,
                temperatures=(sample,),
            ),
        )

        window._selected_node_id = remote_ctx.node_id
        remote_context = window._selected_context()
        self.assertIs(remote_context, remote_ctx)
        remote_state = thermal_render_state(window, remote_context)
        remote_cpu = remote_state.series_for("cpu")
        self.assertTrue(
            remote_cpu is None or not remote_cpu.samples,
            "remote node's thermal series must not inherit local history",
        )

        window._selected_node_id = local_ctx.node_id
        local_context = window._selected_context()
        self.assertIs(local_context, local_ctx)
        local_state = thermal_render_state(window, local_context)
        local_cpu = local_state.series_for("cpu")
        self.assertTrue(
            local_cpu is not None and local_cpu.samples,
            "switching back must restore the local node's history",
        )
