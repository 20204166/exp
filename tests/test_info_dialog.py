"""Focused tests for the structured InfoDialog and its sectioning logic."""

import tkinter as tk
import unittest
from typing import Any
from unittest.mock import Mock, patch

from maintenance.dialogs import InfoDialog, detail_sections
from maintenance.models import ResourceSummary
from tests.support.models import make_summary


def _summary(
    key: str,
    details: tuple[str, ...],
    value: str = "headline",
    title: str | None = None,
) -> ResourceSummary:
    return make_summary(
        key,
        title or {"gpu": "GPU", "network": "Network", "battery": "Battery"}[key],
        value=value,
        subtitle="subtitle",
        percent=None,
        details=details,
    )


class DetailSectionsTests(unittest.TestCase):
    def test_gpu_sections_split_hardware_and_status(self) -> None:
        sections = detail_sections(
            "gpu",
            (
                (
                    "Advanced Micro Devices, Inc. [AMD/ATI] Picasso "
                    "[Radeon Vega Series / Radeon Vega Mobile Series] (rev da)"
                ),
                "GPU usage: 42%",
                "Memory: 512.00 MiB used of 4.00 GiB",
                "Temperature: 56°C",
            ),
        )

        self.assertEqual(sections[0][0], "Hardware")
        self.assertEqual(len(sections[0][1]), 1)
        self.assertEqual(
            sections[0][1][0],
            (
                "",
                (
                    "Advanced Micro Devices, Inc. [AMD/ATI] Picasso "
                    "[Radeon Vega Series / Radeon Vega Mobile Series] (rev da)"
                ),
            ),
        )
        self.assertEqual(sections[1][0], "Status")
        self.assertEqual(
            sections[1][1],
            (
                ("GPU usage", "42%"),
                ("Memory", "512.00 MiB used of 4.00 GiB"),
                ("Temperature", "56°C"),
            ),
        )

    def test_gpu_windows_driver_and_macos_metal_land_in_status(self) -> None:
        windows = detail_sections(
            "gpu",
            ("AMD Radeon RX 6600", "Driver: 31.0.21905.1001", "Memory: 8.00 GiB"),
        )
        self.assertEqual(
            windows[1][1],
            (("Driver", "31.0.21905.1001"), ("Memory", "8.00 GiB")),
        )

        macos = detail_sections(
            "gpu",
            ("Apple M2 Pro", "Metal: Metal 3", "Memory: 16 GB"),
        )
        self.assertEqual(macos[1][1], (("Metal", "Metal 3"), ("Memory", "16 GB")))

    def test_gpu_unavailable_line_lands_in_details(self) -> None:
        sections = detail_sections(
            "gpu", ("GPU information unavailable: query timed out",)
        )

        self.assertEqual(
            sections,
            (("Details", (("GPU information unavailable", "query timed out"),)),),
        )

    def test_network_sections_split_traffic_and_interface(self) -> None:
        sections = detail_sections(
            "network",
            (
                "Download rate: 1.20 MiB/s",
                "Upload rate: 0.30 MiB/s",
                "Received this boot: 4.00 GiB",
                "Sent this boot: 1.00 GiB",
                "Active interface: wlan0",
                "VPN: Not detected",
            ),
        )

        self.assertEqual(sections[0][0], "Traffic")
        self.assertEqual(
            sections[0][1],
            (
                ("Download rate", "1.20 MiB/s"),
                ("Upload rate", "0.30 MiB/s"),
                ("Received this boot", "4.00 GiB"),
                ("Sent this boot", "1.00 GiB"),
            ),
        )
        self.assertEqual(sections[1][0], "Interface")
        self.assertEqual(
            sections[1][1],
            (("Active interface", "wlan0"), ("VPN", "Not detected")),
        )

    def test_network_disconnected_state_is_sectioned(self) -> None:
        sections = detail_sections(
            "network",
            (
                "Download rate: —",
                "Upload rate: —",
                "Received this boot: 0.00 B",
                "Sent this boot: 0.00 B",
                "Active interface: none",
                "VPN: Not detected",
            ),
        )

        self.assertEqual(
            sections[1][1],
            (("Active interface", "none"), ("VPN", "Not detected")),
        )

    def test_battery_real_and_remaining_sectioned(self) -> None:
        sections = detail_sections(
            "battery",
            ("Charge: 75.0%", "Power: Not charging", "Time remaining: ~1h 30m"),
        )

        self.assertEqual(sections[0][0], "Battery")
        self.assertEqual(
            sections[0][1],
            (
                ("Charge", "75.0%"),
                ("Power", "Not charging"),
                ("Time remaining", "~1h 30m"),
            ),
        )

    def test_battery_temperature_lines_use_first_section(self) -> None:
        sections = detail_sections(
            "battery",
            ("CPU: 45°C", "NVMe: 38°C"),
        )

        self.assertEqual(sections[0][0], "Battery")
        self.assertEqual(sections[0][1], (("CPU", "45°C"), ("NVMe", "38°C")))

    def test_battery_unavailable_line_is_kept(self) -> None:
        sections = detail_sections("battery", ("Battery information is unavailable.",))

        self.assertEqual(sections[0][0], "Battery")
        self.assertEqual(
            sections[0][1][0][1],
            "Battery information is unavailable.",
        )

    def test_long_identifier_is_kept_whole(self) -> None:
        long_identifier = "Advanced Micro Devices, Inc. [AMD/ATI] " + "X" * 160
        sections = detail_sections("gpu", (long_identifier,))

        self.assertEqual(sections[0][1][0][1], long_identifier)

    def test_missing_values_keep_dash_text(self) -> None:
        sections = detail_sections(
            "network",
            ("Download rate: —", "Upload rate: —"),
        )

        self.assertEqual(sections[0][1][0][1], "—")

    def test_empty_details_return_no_sections(self) -> None:
        self.assertEqual(detail_sections("gpu", ()), ())
        self.assertEqual(detail_sections("unknown", ()), ())

    def test_unknown_key_uses_single_details_section(self) -> None:
        sections = detail_sections("custom", ("Label: value", "unprefixed"))

        self.assertEqual(
            sections, (("Details", (("Label", "value"), ("", "unprefixed"))),)
        )

    def test_unmatched_prefixed_line_lands_in_details(self) -> None:
        sections = detail_sections("gpu", ("Kernel module: amdgpu",))

        self.assertEqual(sections, (("Details", (("Kernel module", "amdgpu"),)),))


class InfoDialogLayoutContractTests(unittest.TestCase):
    def test_layout_constants_are_declared(self) -> None:
        self.assertGreater(InfoDialog.DETAIL_WRAPLENGTH, 0)
        self.assertEqual(InfoDialog.GEOMETRY, "560x360")
        self.assertEqual(InfoDialog.MIN_SIZE, (500, 320))

    def _open(self, summary: ResourceSummary) -> tuple[Any, list[Any], dict[str, Any]]:
        created: list[Any] = []

        class FakeWidget:
            def __init__(self, *args: object, **kwargs: object) -> None:
                del args
                self.kwargs = kwargs
                created.append(self)

            def pack(self, **options: object) -> None:
                self.pack_options = options

            def config(self, **options: object) -> None:
                self.config_options = options

            def configure(self, **options: object) -> None:
                self.config_options = options

            def bind(self, *args: object) -> None:
                self.bind_args = args

            def create_window(self, *args: object, **kwargs: object) -> int:
                return 1

            def itemconfigure(self, *args: object, **kwargs: object) -> None:
                del args, kwargs

            def yview(self, *args: object) -> None:
                del args

            def set(self, *args: object) -> None:
                del args

            def bbox(self, *args: object) -> tuple[int, int, int, int]:
                return (0, 0, 100, 100)

            def winfo_width(self) -> int:
                return 500

            def destroy(self) -> None:
                self.destroyed = True

        with (
            patch.object(tk.Toplevel, "__init__", lambda self, master=None: None),
            patch.object(InfoDialog, "title"),
            patch.object(InfoDialog, "geometry"),
            patch.object(InfoDialog, "minsize"),
            patch.object(InfoDialog, "configure"),
            patch.object(InfoDialog, "transient"),
            patch.object(InfoDialog, "destroy"),
            patch("maintenance.dialogs.tk.Frame", FakeWidget),
            patch("maintenance.dialogs.tk.Label", FakeWidget),
            patch("maintenance.dialogs.tk.Canvas", FakeWidget),
            patch("maintenance.dialogs.ttk.Button", FakeWidget),
            patch("maintenance.dialogs.ttk.Scrollbar", FakeWidget),
        ):
            dialog = object.__new__(InfoDialog)
            InfoDialog.__init__(
                dialog,
                Mock(),
                summary=summary,
                colors={
                    "background": "#fff",
                    "card": "#fff",
                    "text": "#000",
                    "secondary": "#666",
                    "accent": "#00f",
                    "border": "#eee",
                },
            )
            stubs = {
                "title": dialog.title,
                "geometry": dialog.geometry,
                "minsize": dialog.minsize,
                "configure": dialog.configure,
                "transient": dialog.transient,
                "destroy": dialog.destroy,
            }
        return dialog, created, stubs

    def test_dialog_geometry_and_title_are_set(self) -> None:
        _dialog, _created, stubs = self._open(_summary("gpu", ("Line: one",), value=""))

        self.assertEqual(stubs["title"].call_args.args, ("GPU Details",))
        self.assertEqual(stubs["geometry"].call_args.args, ("560x360",))
        self.assertEqual(stubs["minsize"].call_args.args, (500, 320))

    def test_close_button_always_exists(self) -> None:
        _dialog, created, _stubs = self._open(
            _summary("network", ("Download rate: 1.00 MiB/s", "Upload rate: 0.00 B"))
        )

        close_button = next(
            widget for widget in created if widget.kwargs.get("text") == "Close"
        )
        self.assertTrue(callable(close_button.kwargs["command"]))

    def test_headline_value_rendered_when_non_empty(self) -> None:
        _dialog, created, _stubs = self._open(
            _summary("gpu", ("Hardware line",), value="Radeon Vega Series")
        )

        headlines = [
            widget
            for widget in created
            if widget.kwargs.get("text") == "Radeon Vega Series"
        ]
        self.assertEqual(len(headlines), 1)

    def test_headline_omitted_for_empty_value(self) -> None:
        _dialog, created, _stubs = self._open(
            _summary("gpu", ("Hardware line",), value="")
        )

        headline_labels = [
            widget
            for widget in created
            if widget.kwargs.get("font") == ("Helvetica", 20, "bold")
        ]
        self.assertFalse(
            any(widget.kwargs.get("text") == "" for widget in headline_labels)
        )

    def test_section_titles_and_value_labels_are_created(self) -> None:
        _dialog, created, _stubs = self._open(
            _summary(
                "gpu",
                (
                    "Advanced Micro Devices, Inc. [AMD/ATI] Vega",
                    "Temperature: 56°C",
                ),
            )
        )

        texts = [widget.kwargs.get("text") for widget in created]
        self.assertIn("Hardware", texts)
        self.assertIn("Status", texts)
        self.assertIn("56°C", texts)
        self.assertIn(
            "Advanced Micro Devices, Inc. [AMD/ATI] Vega",
            texts,
        )

    def test_value_and_subtitle_labels_use_detail_wraplength(self) -> None:
        _dialog, created, _stubs = self._open(
            _summary("network", ("Download rate: 1.20 MiB/s", "VPN: Not detected"))
        )

        wrapped = [
            widget
            for widget in created
            if widget.kwargs.get("wraplength") == InfoDialog.DETAIL_WRAPLENGTH
        ]
        self.assertEqual(len(wrapped), 3)
        texts = {widget.kwargs.get("text") for widget in wrapped}
        self.assertIn("subtitle", texts)
        self.assertIn("1.20 MiB/s", texts)
        self.assertIn("Not detected", texts)

    def test_empty_details_show_graceful_message(self) -> None:
        _dialog, created, _stubs = self._open(_summary("gpu", (), value=""))

        texts = [widget.kwargs.get("text") for widget in created]
        self.assertIn("No further details available.", texts)


if __name__ == "__main__":
    unittest.main()
