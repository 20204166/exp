"""Opposer 2 (Repo-Truth Skeptic) counter-test for BUG-20260912-001.

Challenges the candidate's framing that "thermal state must resolve to a
terminal state, not remain no_data" is an existing repo contract.  Repo truth
says otherwise:

- ``docs/CAPABILITY_TRANSPARENCY_2026-09-10.md`` documents "No data yet" as a
  legitimate thermal state ("CPU/GPU/NVMe thermals ... otherwise No data yet
  or Temporarily unavailable on provider failure").
- ``maintenance/models.py`` documents ``CapabilityState.NO_DATA`` as "no
  sample exists yet".
- ``tests/test_temperature_telemetry.py`` locks in ``NO_DATA`` for empty
  inputs (``test_unknown_summary_marks_no_data_state``,
  ``test_empty_scan_keeps_telemetry_in_no_data_state``).
- ``maintenance/ui/thermals_page.py::_should_show`` deliberately keeps a
  ``SUPPORTED``-capability card visible while the series is ``NO_DATA``, and
  ``maintenance/ui/thermal_graph.py`` renders the designed waiting message
  "Waiting for the first sample".

These tests characterize the current, documented, tested behavior so the
opposition record can distinguish "existing contract violated" (bug) from
"new terminal-state contract proposed" (planned fix-forward, per
``docs/plans/2026-09-12-cross-platform-compat-audit.md`` Phase 3).
"""

from __future__ import annotations

import unittest
from typing import Any

from maintenance.cluster import resource_summary_from_dict, resource_summary_to_dict
from maintenance.components.temperature import (
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from maintenance.ui.thermals_page import ThermalsPage
from tests.support.models import make_summary


class RepoTruthNoDataContractTests(unittest.TestCase):
    def test_repeated_empty_supported_summaries_keep_documented_no_data_state(
        self,
    ) -> None:
        """Current repo contract: an empty supported summary stays NO_DATA.

        This is the exact scenario the candidate's RED test drives, asserted
        against the behavior the repo documents and its existing tests lock
        in.  It passes on the current tree, proving the state is stable and
        intentional rather than an accidental regression.
        """

        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(1000):
            telemetry.record_summary("cpu", cpu_card)
        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(
            snapshot.state,
            TemperatureState.NO_DATA,
            "NO_DATA is the documented state for a supported card that has "
            "not yet produced a sample",
        )
        self.assertEqual(snapshot.samples, ())
        self.assertIsNone(snapshot.current_celsius)

    def test_remote_decoded_empty_supported_summary_keeps_no_data_state(
        self,
    ) -> None:
        """The remote path decodes into the same contract and same state.

        ``resource_summary_from_dict`` round-trips a SUPPORTED card with no
        temperatures; recording it keeps ``NO_DATA`` exactly like the local
        path, so the candidate's "local and remote" claim describes one
        documented state machine, not two divergent behaviors.
        """

        telemetry = TemperatureTelemetry()
        remote_card = resource_summary_from_dict(
            resource_summary_to_dict(
                make_summary(
                    "cpu",
                    "CPU",
                    capability=CapabilityState.SUPPORTED,
                    temperatures=(),
                )
            )
        )
        for _ in range(1000):
            telemetry.record_summary("cpu", remote_card)
        snapshot = telemetry.series_snapshot("cpu")
        self.assertEqual(snapshot.state, TemperatureState.NO_DATA)

    def test_thermals_page_keeps_waiting_card_visible_for_no_data(self) -> None:
        """The page's ``_should_show`` deliberately keeps NO_DATA cards shown.

        A SUPPORTED-capability card in NO_DATA state is kept visible so the
        graph can render the designed "Waiting for the first sample" message;
        the page only hides UNSUPPORTED cards.  This is the intentional
        waiting UX the candidate calls a defect.
        """

        page: Any = object.__new__(ThermalsPage)
        page._capabilities = {"cpu": CapabilityState.SUPPORTED}
        self.assertTrue(
            page._should_show("cpu", TemperatureState.NO_DATA),
            "a supported card waiting for its first sample stays visible",
        )
        self.assertFalse(
            page._should_show("cpu", TemperatureState.UNSUPPORTED),
            "an unsupported card is hidden",
        )


if __name__ == "__main__":
    unittest.main()
