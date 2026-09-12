"""Agent 5 (Superpower Evidence Auditor) evidence test for BUG-20260912-001.

Closes two evidence gaps left open by the four opposition sections:

1.  Opposer 1 designed but never ran the end-to-end counter-test. No executed
    proof exists that the *real* scanner emits the PoC's input (a SUPPORTED
    card with empty temperatures) under a sensor-less provider, that this
    real output drives the permanent NO_DATA wait through
    ``TemperatureTelemetry``, and that the Thermals page keeps the waiting
    card visible. Existing repo tests (``tests/test_thermal_card.py``) prove
    a sensor-less psutil yields an empty scan and omitted detail lines, but
    never assert the returned card's capability/temperatures shape, never
    feed real scanner output through telemetry, and never exercise the page
    gate with it.

2.  No opposer tested whether the repo's *declared* thermal capability
    vocabulary could reach the user even if it were wired. The catalog
    declares ``thermals/sensors`` as ``NOT_VERIFIED_ON_NATIVE_PLATFORM`` on
    Darwin/Windows, but nothing verifies how the telemetry state machine and
    the page gate would treat that state if a provider or remote peer ever
    sent it.

No app code or normal repo tests are edited by this file.
"""

from __future__ import annotations

import unittest
from typing import Any

from maintenance.components.catalog import ResourceFeatureCatalog
from maintenance.components.temperature import (
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState, capability_label
from maintenance.ui.thermals_page import ThermalsPage
from tests.support.models import make_summary
from tests.support.scanner import (
    make_baseline_psutil,
    make_scanner,
    scanner_environment,
)

_EMPTY_READ_HORIZONS = (1, 10, 100, 1000)


def _waiting_page(capabilities: dict[str, CapabilityState]) -> Any:
    """Build a ThermalsPage gate without a live Tk root (folder pattern)."""

    page: Any = object.__new__(ThermalsPage)
    page._capabilities = capabilities
    return page


class RealPipelineEvidenceTests(unittest.TestCase):
    """Executed end-to-end evidence for the candidate's reachability claim."""

    def test_sensorless_real_scan_yields_supported_card_with_empty_temps(
        self,
    ) -> None:
        """A real CPU scan with no sensors emits the PoC's exact input.

        Runs the real ``SystemScanner.scan_component("cpu")`` on the real
        platform (Linux) with a psutil fake whose ``sensors_temperatures``
        returns an empty dict -- no platform patching. Existing tests only
        assert detail lines are omitted; this asserts the card shape the
        candidate's PoC assumes.
        """

        scanner = make_scanner()
        fake = make_baseline_psutil(sensors_temperatures=dict)

        with scanner_environment(scanner, fake, trash_size=0):
            summary = scanner.scan_component("cpu")

        self.assertEqual(summary.capability, CapabilityState.SUPPORTED)
        self.assertEqual(summary.temperatures, ())
        self.assertFalse(summary.failed)

    def test_real_scan_output_drives_permanent_no_data_wait(self) -> None:
        """Real scanner output keeps telemetry in NO_DATA at every horizon.

        Feeds the real scan summary through ``TemperatureTelemetry`` at 1,
        10, 100, and 1000 consecutive reads and asserts the state is NO_DATA
        at each horizon (no hidden transition), then asserts the Thermals
        page gate keeps the card visible so the graph renders the waiting
        message. This is the end-to-end chain Opposer 1 designed but never
        executed.
        """

        scanner = make_scanner()
        fake = make_baseline_psutil(sensors_temperatures=dict)

        with scanner_environment(scanner, fake, trash_size=0):
            summary = scanner.scan_component("cpu")

        telemetry = TemperatureTelemetry()
        for horizon in _EMPTY_READ_HORIZONS:
            for _ in range(horizon):
                telemetry.record_summary("cpu", summary)
            self.assertEqual(
                telemetry.series_snapshot("cpu").state,
                TemperatureState.NO_DATA,
                f"state must still be NO_DATA after {horizon} empty reads",
            )

        page = _waiting_page({"cpu": CapabilityState.SUPPORTED})
        self.assertTrue(
            page._should_show("cpu", TemperatureState.NO_DATA),
            "a supported card with no samples stays visible and waiting",
        )

    def test_darwin_branch_fails_closed_to_supported_card_with_empty_temps(
        self,
    ) -> None:
        """The Darwin acquisition branch fails closed while the card stays up.

        Selects the Darwin branch via the scanner's platform seam. On this
        host ``read_smc_temperatures`` fails closed through its own
        ``_load_io`` guard (real ``sys.platform`` is not darwin), so no IOKit
        or subprocess is touched. This executes the fail-closed shape the
        candidate claims for macOS; it is branch-selection evidence, not
        native macOS proof.
        """

        scanner = make_scanner()
        fake = make_baseline_psutil(sensors_temperatures=dict)

        with scanner_environment(scanner, fake, trash_size=0, system="Darwin"):
            summary = scanner.scan_component("cpu")

        self.assertEqual(summary.capability, CapabilityState.SUPPORTED)
        self.assertEqual(summary.temperatures, ())
        self.assertFalse(summary.failed)


class DeclaredVocabularyEvidenceTests(unittest.TestCase):
    """Whether the repo's declared thermal capability can reach the user."""

    def test_declared_thermal_capability_state_cannot_reach_the_user(self) -> None:
        """The declared Darwin/Windows thermal state has no runtime mapping.

        The catalog declares ``thermals/sensors`` as
        ``NOT_VERIFIED_ON_NATIVE_PLATFORM`` on Darwin/Windows and the label
        wording exists ("Not verified on this platform"), but the telemetry
        state machine maps every non-UNSUPPORTED, non-failed, empty summary
        to NO_DATA, and the page gate keeps such a card visible. So even if
        a provider or remote peer sent the declared state, the user would
        still see the indefinite waiting presentation.
        """

        catalog = ResourceFeatureCatalog()
        declaration = next(
            item
            for item in catalog.CAPABILITY_DECLARATIONS
            if item.component == "thermals" and item.metric == "sensors"
        )
        self.assertEqual(declaration.state_for("Linux"), CapabilityState.NO_DATA)
        self.assertEqual(
            declaration.state_for("Darwin"),
            CapabilityState.NOT_VERIFIED_ON_NATIVE_PLATFORM,
        )
        self.assertEqual(
            declaration.state_for("Windows"),
            CapabilityState.NOT_VERIFIED_ON_NATIVE_PLATFORM,
        )
        self.assertEqual(
            capability_label(CapabilityState.NOT_VERIFIED_ON_NATIVE_PLATFORM),
            "Not verified on this platform",
        )

        telemetry = TemperatureTelemetry()
        declared = make_summary(
            "cpu",
            "CPU",
            capability=CapabilityState.NOT_VERIFIED_ON_NATIVE_PLATFORM,
            temperatures=(),
        )
        for _ in range(1000):
            telemetry.record_summary("cpu", declared)

        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.NO_DATA
        )
        page = _waiting_page({"cpu": CapabilityState.NOT_VERIFIED_ON_NATIVE_PLATFORM})
        self.assertTrue(
            page._should_show("cpu", TemperatureState.NO_DATA),
            "even the declared not-verified state renders as a visible wait",
        )


if __name__ == "__main__":
    unittest.main()
