import unittest

from maintenance.components import GpuDetector, ScanCoordinator


class GpuDetectorTests(unittest.TestCase):
    def test_gpu_detector_prefers_platform_specific_loader(self) -> None:
        calls: list[str] = []

        def nvidia_loader() -> tuple[str, ...] | None:
            calls.append("nvidia")
            return None

        def mac_loader() -> tuple[str, ...]:
            calls.append("mac")
            return ("mac",)

        def windows_loader() -> tuple[str, ...]:
            calls.append("windows")
            return ("windows",)

        def linux_loader() -> tuple[str, ...]:
            calls.append("linux")
            return ("linux",)

        detector = GpuDetector(
            system=lambda: "Linux",
            nvidia_loader=nvidia_loader,
            mac_loader=mac_loader,
            windows_loader=windows_loader,
            linux_loader=linux_loader,
        )

        self.assertEqual(detector.detect(), ("linux",))
        self.assertEqual(calls, ["nvidia", "linux"])


class ScanCoordinatorTests(unittest.TestCase):
    def test_scan_coordinator_defers_rerun_until_completion(self) -> None:
        coordinator = ScanCoordinator()

        generation, started = coordinator.begin()
        self.assertTrue(started)
        self.assertEqual(generation, 1)

        repeated_generation, repeated_started = coordinator.begin()
        self.assertFalse(repeated_started)
        self.assertEqual(repeated_generation, 1)

        finished, rerun_requested = coordinator.finish(generation)
        self.assertTrue(finished)
        self.assertTrue(rerun_requested)

        next_generation, next_started = coordinator.begin()
        self.assertTrue(next_started)
        self.assertEqual(next_generation, 2)


if __name__ == "__main__":
    unittest.main()
