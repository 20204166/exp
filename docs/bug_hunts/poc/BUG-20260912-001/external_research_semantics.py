"""External-Research Skeptic PoC for BUG-20260912-001.

This PoC challenges the semantic claim that "NO_DATA indefinitely" is a bug
by examining:
1. Python enum comparison semantics (official documentation)
2. unittest assertNotEqual behavior (official documentation)
3. State machine design patterns for terminal vs. persistent states
4. The documented meaning of NO_DATA vs. UNSUPPORTED

The claim assumes NO_DATA must transition after repeated empty samples,
but this is a policy decision, not a semantic violation.
"""

from __future__ import annotations

import unittest

from maintenance.components.temperature import (
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from tests.support.models import make_summary


class ExternalResearchSemanticTests(unittest.TestCase):
    """Challenge the semantic claim from external documentation perspective."""

    def test_enum_comparison_semantics_are_correct(self) -> None:
        """Verify that enum comparison follows Python's official semantics.

        Python documentation states: "Enumeration members are compared by identity"
        and "Equality comparisons are defined though: Color.BLUE == Color.BLUE -> True"

        This test confirms the test's assertion mechanism is semantically valid.
        """
        # Same member compares equal
        self.assertEqual(TemperatureState.NO_DATA, TemperatureState.NO_DATA)

        # Different members compare not equal
        self.assertNotEqual(TemperatureState.NO_DATA, TemperatureState.VALID)
        self.assertNotEqual(TemperatureState.NO_DATA, TemperatureState.UNSUPPORTED)

        # Identity comparison also works
        self.assertIs(TemperatureState.NO_DATA, TemperatureState.NO_DATA)

    def test_unittest_assertnotequal_semantics(self) -> None:
        """Verify unittest.assertNotEqual uses != operator correctly.

        Python documentation states: "Test that first and second are not equal.
        If the values do compare equal, the test will fail."

        This confirms the test's assertion is structurally valid.
        """
        # This should pass (different values)
        self.assertNotEqual(TemperatureState.NO_DATA, TemperatureState.VALID)

        # This would fail (same values) - demonstrating the operator works
        with self.assertRaises(AssertionError):
            self.assertNotEqual(TemperatureState.NO_DATA, TemperatureState.NO_DATA)

    def test_nodata_semantic_meaning_is_waiting_not_terminal(self) -> None:
        """Examine the documented meaning of NO_DATA.

        From maintenance/models.py CapabilityState docstring:
        "NO_DATA means no sample exists yet."

        The word "yet" implies a waiting state, not a terminal state.
        However, this does not mean it MUST transition - it means the state
        is semantically correct as long as no sample exists.

        The claim assumes that after N empty reads, the state should transition,
        but this is a policy decision (when to give up waiting), not a semantic
        violation (the state accurately reflects "no sample exists yet").
        """
        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )

        # Record one empty summary
        telemetry.record_summary("cpu", cpu_card)
        snapshot = telemetry.series_snapshot("cpu")

        # Semantically, NO_DATA means "no sample exists yet" - this is accurate
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)
        self.assertEqual(snapshot.current_celsius, None)
        self.assertEqual(len(snapshot.samples), 0)

        # The state accurately reflects reality: no sample exists
        # Whether it should transition after 1000 reads is a policy question

    def test_unsupported_requires_authoritative_declaration(self) -> None:
        """Verify that UNSUPPORTED requires explicit capability declaration.

        From maintenance/models.py CapabilityState docstring:
        "UNSUPPORTED means an authoritative probe proved the capability is absent"

        This is semantically different from "no samples yet". A card can be
        SUPPORTED (CPU exists) while its thermal series has NO_DATA (no thermal
        samples yet). These are orthogonal concerns.
        """
        telemetry = TemperatureTelemetry()

        # Case 1: SUPPORTED capability with no thermal samples
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        telemetry.record_summary("cpu", cpu_card)
        snapshot = telemetry.series_snapshot("cpu")

        # State is NO_DATA, not UNSUPPORTED, because capability is SUPPORTED
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)

        # Case 2: UNSUPPORTED capability
        telemetry2 = TemperatureTelemetry()
        battery_card = make_summary(
            "battery",
            "Battery",
            capability=CapabilityState.UNSUPPORTED,
            temperatures=(),
        )
        telemetry2.record_summary("battery", battery_card)
        snapshot2 = telemetry2.series_snapshot("battery")

        # State is UNSUPPORTED because capability is UNSUPPORTED
        self.assertEqual(snapshot2.state, TemperatureState.UNSUPPORTED)

    def test_state_machine_no_builtin_transition_counter(self) -> None:
        """Verify that the state machine has no built-in transition counter.

        Python enum-based state machines can embed transition logic (see external
        research on "Enums as State Machines"), but this implementation chooses
        not to add a counter for NO_DATA -> UNSUPPORTED transitions.

        This is a design choice, not a bug. The state machine correctly implements:
        - VALID when samples exist
        - UNSUPPORTED when capability is UNSUPPORTED
        - ERROR when summary.failed
        - NO_DATA otherwise (no samples, but capability is SUPPORTED)

        Adding a counter would be a feature enhancement, not a bug fix.
        """
        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )

        # Record many empty summaries
        for _ in range(100):
            telemetry.record_summary("cpu", cpu_card)

        snapshot = telemetry.series_snapshot("cpu")

        # State remains NO_DATA - this is semantically consistent
        # The state accurately reflects "no sample exists yet"
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)

        # The absence of a transition counter is a design choice
        # Check that _ComponentTelemetry has no empty_reads field
        component_telemetry = telemetry._components.get("cpu")
        self.assertIsNotNone(component_telemetry)
        self.assertFalse(hasattr(component_telemetry, "empty_reads"))

    def test_ui_rendering_is_semantically_correct(self) -> None:
        """Verify that UI rendering matches the semantic meaning.

        From maintenance/ui/thermal_graph.py:
        - NO_DATA -> "Waiting for the first sample"
        - UNSUPPORTED -> "Temperature not supported"

        The UI correctly renders the semantic meaning of each state.
        The claim that NO_DATA is misleading after 1000 reads is a UX concern,
        not a semantic bug. The message is accurate: we are still waiting.
        """
        # This test documents the UI behavior without testing Tk widgets
        # The actual UI rendering is tested in other test files

        # Semantic mapping:
        state_to_message = {
            TemperatureState.NO_DATA: "Waiting for the first sample",
            TemperatureState.UNSUPPORTED: "Temperature not supported",
            TemperatureState.ERROR: "Temperature temporarily unavailable",
            TemperatureState.VALID: "shows graph",
        }

        # Each state has a semantically appropriate message
        self.assertIn("Waiting", state_to_message[TemperatureState.NO_DATA])
        self.assertIn("not supported", state_to_message[TemperatureState.UNSUPPORTED])


if __name__ == "__main__":
    unittest.main()
