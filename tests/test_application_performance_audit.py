"""Tests for the application observability report tool."""

import unittest

from tools.application_performance_audit import report_payload


class ApplicationPerformanceAuditTests(unittest.TestCase):
    def test_report_projects_observer_distributions_without_recomputing_them(
        self,
    ) -> None:
        payload = report_payload(
            {
                "observability": {
                    "metrics": [
                        {
                            "target": "ui:render:dashboard",
                            "count": 4,
                            "successes": 4,
                            "failures": 0,
                            "cancellations": 0,
                            "in_flight": 0,
                            "peak_in_flight": 1,
                            "distribution": {"p50": 0.01, "p95": 0.02, "p99": 0.03},
                        }
                    ]
                }
            }
        )

        self.assertEqual(payload["metrics"][0]["target"], "ui:render:dashboard")
        self.assertEqual(payload["metrics"][0]["distribution"]["p99"], 0.03)


if __name__ == "__main__":
    unittest.main()
