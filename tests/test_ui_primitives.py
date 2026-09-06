"""Focused regression tests for the shared UI presentation primitives."""

import tkinter as tk
import unittest
from typing import Any, ClassVar
from unittest.mock import Mock, patch

from maintenance.models import ResourceSummary
from maintenance.ui import PendingTransition, scan_status
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.styles import configure_app_styles
from window import AppWindow


class FakeControl:
    def __init__(self) -> None:
        self.options: dict[str, Any] = {}

    def config(self, **options: Any) -> None:
        self.options.update(options)


class DesignTokenParityTests(unittest.TestCase):
    def test_window_colour_tokens_come_from_shared_styles(self) -> None:
        expected = {
            "BACKGROUND": "background",
            "CARD_BACKGROUND": "card",
            "TEXT_PRIMARY": "text",
            "TEXT_SECONDARY": "secondary",
            "ACCENT": "accent",
            "ACCENT_ACTIVE": "accent_active",
            "BORDER": "border",
        }
        for attribute, token in expected.items():
            with self.subTest(attribute=attribute):
                self.assertEqual(
                    getattr(AppWindow, attribute),
                    ui_styles.COLORS[token],
                )

    def test_window_font_tokens_come_from_shared_styles(self) -> None:
        expected = {
            "TITLE_FONT": "title",
            "SECTION_FONT": "section",
            "BODY_FONT": "body",
            "BUTTON_FONT": "button",
            "DANGER_BUTTON_FONT": "danger_button",
            "STATUS_FONT": "status",
        }
        for attribute, token in expected.items():
            with self.subTest(attribute=attribute):
                self.assertEqual(
                    getattr(AppWindow, attribute),
                    ui_styles.FONTS[token],
                )


class FakeStyle:
    def __init__(self) -> None:
        self.configured: dict[str, dict[str, Any]] = {}
        self.mapped: dict[str, dict[str, Any]] = {}

    def configure(self, name: str, **options: Any) -> None:
        self.configured[name] = options

    def map(self, name: str, **options: Any) -> None:
        self.mapped[name] = options


class StyleRegistrationTests(unittest.TestCase):
    def test_style_registration_uses_shared_tokens(self) -> None:
        style = FakeStyle()

        configure_app_styles(style)

        self.assertIn("App.TFrame", style.configured)
        self.assertIn("Title.TLabel", style.configured)
        self.assertIn("Primary.TButton", style.configured)
        self.assertIn("Danger.TButton", style.configured)
        self.assertIn("Ready.Status.TLabel", style.configured)
        self.assertIn("Busy.Status.TLabel", style.configured)
        self.assertIn("Analysis.Horizontal.TProgressbar", style.configured)
        self.assertIn("Complete.Horizontal.TProgressbar", style.configured)
        self.assertIn("Card.Horizontal.TProgressbar", style.configured)

    def test_primary_button_registers_exact_colours(self) -> None:
        style = FakeStyle()

        configure_app_styles(style)

        self.assertEqual(
            style.configured["Primary.TButton"]["background"],
            ui_styles.COLORS["accent"],
        )
        self.assertEqual(
            style.mapped["Primary.TButton"]["background"],
            [
                ("active", ui_styles.COLORS["accent_active"]),
                ("disabled", ui_styles.COLORS["primary_disabled"]),
            ],
        )

    def test_neutral_button_registers_secondary_palette(self) -> None:
        style = FakeStyle()

        configure_app_styles(style)

        configured = style.configured["Neutral.TButton"]
        self.assertEqual(configured["background"], ui_styles.COLORS["button_bg"])
        self.assertEqual(configured["foreground"], ui_styles.COLORS["text"])
        self.assertEqual(configured["bordercolor"], ui_styles.COLORS["border"])
        self.assertEqual(
            style.mapped["Neutral.TButton"]["background"],
            [
                ("active", ui_styles.COLORS["button_bg_active"]),
                ("disabled", ui_styles.COLORS["disabled"]),
            ],
        )

    def test_status_and_bar_styles_use_success_token(self) -> None:
        style = FakeStyle()

        configure_app_styles(style)

        self.assertEqual(
            style.configured["Ready.Status.TLabel"]["foreground"],
            ui_styles.COLORS["success"],
        )
        self.assertEqual(
            style.configured["Complete.Horizontal.TProgressbar"]["background"],
            ui_styles.COLORS["success"],
        )


class ScanStatusPresentationTests(unittest.TestCase):
    def test_progress_text_formats_count_and_total(self) -> None:
        self.assertEqual(
            scan_status.progress_text("Scanning CPU...", 1, 6),
            "●  Scanning CPU... (1/6)",
        )

    def test_scanning_sets_busy_wording_and_style(self) -> None:
        label = Mock()

        scan_status.apply_scanning(label)

        label.config.assert_called_once_with(
            text="●  Scanning...",
            style="Busy.Status.TLabel",
        )

    def test_step_advances_bar_and_status(self) -> None:
        label = Mock()
        bar = Mock()

        scan_status.apply_step(label, bar, "Scanning CPU...", 1, 6)

        bar.config.assert_called_once_with(value=1)
        label.config.assert_called_once_with(text="●  Scanning CPU... (1/6)")

    def test_cancelling_sets_standard_wording(self) -> None:
        label = Mock()

        scan_status.apply_cancelling(label)

        label.config.assert_called_once_with(text="●  Cancelling...")

    def test_complete_fills_bar_green_and_shows_complete(self) -> None:
        label = Mock()
        bar = Mock()

        scan_status.apply_complete(label, bar, 6)

        bar.config.assert_called_once_with(
            value=6,
            style="Complete.Horizontal.TProgressbar",
        )
        label.config.assert_called_once_with(
            text="● Scan complete",
            style="Ready.Status.TLabel",
        )

    def test_ready_sets_idle_wording_and_style(self) -> None:
        label = Mock()

        scan_status.apply_ready(label)

        label.config.assert_called_once_with(
            text="●  Ready",
            style="Ready.Status.TLabel",
        )

    def test_reset_empties_analysis_bar(self) -> None:
        bar = Mock()

        scan_status.apply_reset(bar)

        bar.config.assert_called_once_with(
            value=0,
            style="Analysis.Horizontal.TProgressbar",
        )


class MetricRowPrimitiveTests(unittest.TestCase):
    def test_metric_row_uses_supplied_factories_and_options(self) -> None:
        row = Mock()
        label = Mock()
        frame_factory = Mock(return_value=row)
        label_factory = Mock(return_value=label)

        returned = ui_layout.metric_row(
            "parent",
            "Load",
            "45%",
            frame_cls=frame_factory,
            label_cls=label_factory,
            bg="#fff",
            label_fg="#666",
            value_fg="#000",
            font=("Helvetica", 9),
            wraplength=430,
        )

        self.assertEqual(returned, (row, label, label))
        frame_factory.assert_called_once_with("parent", bg="#fff")
        row.pack.assert_called_once_with(fill="x", pady=1)
        label_factory.assert_any_call(
            row,
            text="Load",
            bg="#fff",
            fg="#666",
            font=("Helvetica", 9),
            anchor="w",
        )
        label_factory.assert_any_call(
            row,
            text="45%",
            bg="#fff",
            fg="#000",
            font=("Helvetica", 9),
            anchor="e",
            wraplength=430,
        )

    def test_metric_row_applies_justify_only_when_requested(self) -> None:
        row = Mock()
        label = Mock()
        label_factory = Mock(return_value=label)

        ui_layout.metric_row(
            "parent",
            "Load",
            "45%",
            frame_cls=Mock(return_value=row),
            label_cls=label_factory,
            bg="#fff",
            label_fg="#666",
            value_fg="#000",
            font=("Helvetica", 9),
            justify="left",
        )

        label_factory.assert_any_call(
            row,
            text="45%",
            bg="#fff",
            fg="#000",
            font=("Helvetica", 9),
            anchor="e",
            justify="left",
        )

    def test_metric_row_applies_cursor_to_clickable_labels(self) -> None:
        label = Mock()
        frame_factory = Mock(return_value=Mock())
        label_factory = Mock(return_value=label)

        ui_layout.metric_row(
            "parent",
            "Load",
            "45%",
            frame_cls=frame_factory,
            label_cls=label_factory,
            bg="#fff",
            label_fg="#666",
            value_fg="#000",
            font=("Helvetica", 9),
            cursor="hand2",
        )

        label.config.assert_called_once_with(cursor="hand2")


class ScrollableAreaPrimitiveTests(unittest.TestCase):
    class FakeCanvas:
        def __init__(self) -> None:
            self.height = 200
            self.config_calls: list[dict[str, Any]] = []
            self.pack_kwargs: dict[str, Any] = {}
            self.create_window_called = False

        def configure(self, **options: Any) -> None:
            self.config_calls.append(options)

        def create_window(self, *args: Any, **kwargs: Any) -> int:
            self.create_window_called = True
            return 1

        def bbox(self, *args: Any) -> tuple[int, int, int, int]:
            return (0, 0, 100, 100)

        def winfo_width(self) -> int:
            return 300

        def winfo_height(self) -> int:
            return self.height

        def itemconfigure(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def pack(self, **options: Any) -> None:
            self.pack_kwargs = options

        def bind(self, *args: Any) -> None:
            del args

        def yview(self, *args: Any) -> None:
            del args

        def set(self, *args: Any) -> None:
            del args

    class FakeInner:
        def __init__(self) -> None:
            self.reqheight = 100

        def winfo_reqheight(self) -> int:
            return self.reqheight

        def bind(self, *args: Any) -> None:
            del args

    class FakeScrollbar:
        def __init__(self) -> None:
            self.mapped = True
            self.pack_calls: list[dict[str, Any]] = []
            self.pack_forget_calls = 0

        def pack(self, **options: Any) -> None:
            self.mapped = True
            self.pack_calls.append(options)

        def pack_forget(self) -> None:
            self.mapped = False
            self.pack_forget_calls += 1

        def winfo_ismapped(self) -> bool:
            return self.mapped

        def set(self, *args: Any) -> None:
            del args

    def _area(self, auto_hide: bool) -> tuple[Any, Any, Any, Any]:
        canvas = self.FakeCanvas()
        inner = self.FakeInner()
        scrollbar = self.FakeScrollbar()

        def frame_factory(_parent: Any, **kwargs: Any) -> Any:
            del kwargs
            return inner

        def canvas_factory(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            return canvas

        def scrollbar_factory(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            return scrollbar

        _canvas, _inner, refresh = ui_layout.scrollable_area(
            "parent",
            bg="#fff",
            frame_cls=frame_factory,
            canvas_cls=canvas_factory,
            scrollbar_cls=scrollbar_factory,
            frame_kwargs={"bg": "#fff"},
            auto_hide=auto_hide,
        )
        return refresh, canvas, inner, scrollbar

    def test_scrollable_area_packs_canvas_and_scrollbar(self) -> None:
        _refresh, canvas, _inner, scrollbar = self._area(auto_hide=False)

        self.assertTrue(canvas.create_window_called)
        self.assertEqual(canvas.pack_kwargs["side"], "left")
        self.assertTrue(scrollbar.mapped)

    def test_scrollbar_is_guttered_from_content(self) -> None:
        _refresh, _canvas, _inner, scrollbar = self._area(auto_hide=False)

        self.assertEqual(
            scrollbar.pack_calls[0],
            {
                "side": "right",
                "fill": "y",
                "padx": (ui_layout.SCROLLBAR_GUTTER, 0),
            },
        )

    def test_auto_hide_reshow_keeps_gutter(self) -> None:
        refresh, _canvas, inner, scrollbar = self._area(auto_hide=True)
        inner.reqheight = 300

        refresh()

        self.assertTrue(scrollbar.mapped)
        self.assertEqual(scrollbar.pack_calls[-1]["side"], "right")
        self.assertEqual(
            scrollbar.pack_calls[-1]["padx"],
            (ui_layout.SCROLLBAR_GUTTER, 0),
        )

    def test_auto_hide_hides_scrollbar_when_content_fits(self) -> None:
        refresh, _canvas, _inner, scrollbar = self._area(auto_hide=True)
        refresh()

        self.assertFalse(scrollbar.mapped)
        self.assertEqual(scrollbar.pack_forget_calls, 1)

    def test_auto_hide_reshows_scrollbar_when_content_overflows(self) -> None:
        refresh, _canvas, inner, scrollbar = self._area(auto_hide=True)
        inner.reqheight = 300

        refresh()

        self.assertTrue(scrollbar.mapped)
        self.assertEqual(scrollbar.pack_calls[-1]["side"], "right")


class DashboardHeaderTests(unittest.TestCase):
    class Factory:
        def __init__(self) -> None:
            self.labels: list[Any] = []
            self.frames: list[Any] = []

        def label(self, *args: Any, **kwargs: Any) -> Any:
            del args
            label = Mock()
            label.kwargs = kwargs
            label.pack = Mock()
            self.labels.append(label)
            return label

        def frame(self, *args: Any, **kwargs: Any) -> Any:
            del args
            frame = Mock()
            frame.kwargs = kwargs
            frame.pack = Mock()
            self.frames.append(frame)
            return frame

    def _render(
        self, node_title: str | None
    ) -> tuple[Any, "DashboardHeaderTests.Factory"]:
        factory = self.Factory()
        actions = ui_layout.dashboard_header(
            "parent",
            title="System Analyzer",
            description="Scan your system.",
            frame_cls=factory.frame,
            label_cls=factory.label,
            wrap=680,
            node_title=node_title,
        )
        return actions, factory

    def test_header_renders_title_and_description_without_node(self) -> None:
        _actions, factory = self._render(None)

        title = next(
            label
            for label in factory.labels
            if label.kwargs.get("style") == "Title.TLabel"
        )
        self.assertEqual(title.kwargs["text"], "System Analyzer")
        description = next(
            label
            for label in factory.labels
            if label.kwargs.get("style") == "Description.TLabel"
        )
        self.assertEqual(description.kwargs["wraplength"], 680)
        node_labels = [
            label
            for label in factory.labels
            if label.kwargs.get("style") == "Node.TLabel"
        ]
        self.assertEqual(node_labels, [])

    def test_header_with_node_title_renders_uppercase_node_label(self) -> None:
        _actions, factory = self._render("Gaming Node")

        node = next(
            label
            for label in factory.labels
            if label.kwargs.get("style") == "Node.TLabel"
        )
        self.assertEqual(node.kwargs["text"], "GAMING NODE")
        node.pack.assert_called_once_with(anchor="w", pady=(2, 0))

    def test_header_returns_actions_frame_packed_right(self) -> None:
        actions, factory = self._render(None)

        self.assertIs(actions, factory.frames[-1])
        actions.pack.assert_called_once_with(side="right", padx=(20, 0))

    def test_header_exposes_an_unpacked_discovery_status_label(self) -> None:
        actions, factory = self._render(None)

        discovery = actions._dashboard_discovery_label
        self.assertIn(discovery, factory.labels)
        self.assertEqual(discovery.kwargs["text"], "")
        self.assertEqual(discovery.kwargs["style"], "Description.TLabel")
        discovery.pack.assert_not_called()

    def test_any_node_title_renders_through_same_primitive(self) -> None:
        for node_title in ("This Node", "Node 1", "Node 2", "Gaming Node"):
            with self.subTest(node_title=node_title):
                _actions, factory = self._render(node_title)
                node = next(
                    label
                    for label in factory.labels
                    if label.kwargs.get("style") == "Node.TLabel"
                )
                self.assertEqual(node.kwargs["text"], node_title.upper())


class CardHoverPresentationTests(unittest.TestCase):
    def _card(self) -> Any:
        from maintenance.dialogs import ResourceCard

        card: Any = object.__new__(ResourceCard)
        card.colors = {"card": "#fff", "border": "#eee", "accent": "#4F46E5"}
        card.configure = Mock()
        return card

    def test_hover_highlights_border_with_accent(self) -> None:
        card = self._card()

        card._set_hover()

        card.configure.assert_called_once_with(highlightbackground="#4F46E5")

    def test_leave_restores_border(self) -> None:
        card = self._card()

        card._set_hover()
        card._clear_hover()

        card.configure.assert_called_with(highlightbackground="#eee")


class ResizeAwareTests(unittest.TestCase):
    class FakeWidget:
        def __init__(self) -> None:
            self.bindings: dict[str, Any] = {}
            self.idle: Any = None

        def bind(self, sequence: str, handler: Any) -> None:
            self.bindings[sequence] = handler

        def after_idle(self, handler: Any) -> str:
            self.idle = handler
            return "idle-1"

    def test_configure_coalesces_into_one_idle_layout_pass(self) -> None:
        widget = self.FakeWidget()
        calls: list[Any] = []
        ui_layout.resize_aware(widget, lambda w: calls.append(w))

        on_configure = widget.bindings["<Configure>"]
        on_configure()
        on_configure()
        on_configure()

        self.assertEqual(calls, [])
        widget.idle()
        self.assertEqual(calls, [widget])
        on_configure()
        self.assertEqual(calls, [widget])

    def test_handler_error_after_destroy_is_swallowed(self) -> None:
        widget = self.FakeWidget()
        raised = False

        def handler(_widget: Any) -> None:
            nonlocal raised
            raised = True
            raise tk.TclError("widget destroyed")

        ui_layout.resize_aware(widget, handler)
        widget.bindings["<Configure>"]()
        widget.idle()

        self.assertTrue(raised)


class FitWrapToWidthTests(unittest.TestCase):
    def test_wrap_narrows_to_container_but_never_exceeds_max(self) -> None:
        label = Mock()
        handler = ui_layout.fit_wrap_to_width(label, 800)

        class Container:
            def __init__(self, width: int) -> None:
                self._width = width

            def winfo_width(self) -> int:
                return self._width

        handler(Container(852))
        label.configure.assert_called_with(wraplength=800)

        handler(Container(700))
        label.configure.assert_called_with(wraplength=692)

        handler(Container(50))
        label.configure.assert_called_with(wraplength=240)


class NextWrapWidthTests(unittest.TestCase):
    def test_exact_fit_shrink_never_clips(self) -> None:
        self.assertEqual(ui_layout.next_wrap_width(290, 264), 254)

    def test_small_growth_is_deferred(self) -> None:
        self.assertIsNone(ui_layout.next_wrap_width(310, 264))

    def test_growth_beyond_hysteresis_is_applied(self) -> None:
        self.assertEqual(ui_layout.next_wrap_width(315, 264), 279)

    def test_same_width_is_noop(self) -> None:
        self.assertIsNone(ui_layout.next_wrap_width(300, 264))

    def test_narrow_width_still_fits(self) -> None:
        self.assertEqual(ui_layout.next_wrap_width(50, 0), 14)

    def test_unmeasured_width_is_skipped(self) -> None:
        self.assertIsNone(ui_layout.next_wrap_width(1, 0))

    def test_default_margin(self) -> None:
        self.assertEqual(ui_layout.next_wrap_width(300, 0), 264)

    def test_custom_margin_and_hysteresis(self) -> None:
        self.assertEqual(
            ui_layout.next_wrap_width(200, 0, margin=20, hysteresis=4),
            180,
        )


class CardRewrapPresentationTests(unittest.TestCase):
    def _card(self, width: int) -> Any:
        from maintenance.dialogs import ResourceCard

        card: Any = object.__new__(ResourceCard)
        card.value_label = FakeControl()
        card.subtitle_label = FakeControl()
        card.metric_rows = []
        card.winfo_width = Mock(return_value=width)
        return card

    def test_card_rewrap_fits_headline_and_subtitle_to_width(self) -> None:
        card = self._card(300)

        card._rewrap()

        self.assertEqual(card.value_label.options["wraplength"], 264)
        self.assertEqual(card.subtitle_label.options["wraplength"], 264)

    def test_card_rewrap_wraps_metric_values_with_label_space(self) -> None:
        card = self._card(300)
        metric_value = FakeControl()
        card.metric_rows = [("row", "name", metric_value)]

        card._rewrap()

        self.assertEqual(metric_value.options["wraplength"], 134)

    def test_card_rewrap_without_metric_rows_is_safe(self) -> None:
        card = self._card(300)
        card.metric_rows = []

        card._rewrap()

        self.assertEqual(card.value_label.options["wraplength"], 264)

    def test_metric_wrap_has_floor(self) -> None:
        card = self._card(120)
        card._last_card_wrap = 84
        card._rewrap()

        self.assertEqual(card._metric_wrap(), 60)

    def test_render_metrics_applies_wrap_to_new_rows(self) -> None:
        from maintenance.dialogs import ResourceCard

        card: Any = object.__new__(ResourceCard)
        card.colors = {"card": "#fff", "secondary": "#666", "text": "#000"}
        card.metric_rows = []
        card.metrics_frame = Mock()
        card._last_card_wrap = 264
        value = Mock()
        with patch(
            "maintenance.ui.layout.metric_row",
            return_value=(Mock(), Mock(), value),
        ):
            card._render_metrics(
                ResourceSummary(
                    key="cpu",
                    title="CPU",
                    value="x",
                    subtitle="s",
                    percent=5.0,
                    details=("Download rate: 1.20 MiB/s",),
                )
            )

        value.config.assert_called_once_with(wraplength=134)
        self.assertEqual(len(card.metric_rows), 1)

    def test_card_rewrap_is_noop_for_same_width(self) -> None:
        card = self._card(300)
        card._last_card_wrap = 264

        card._rewrap()

        self.assertNotIn("wraplength", card.value_label.options)

    def test_card_rewrap_deferred_for_small_growth(self) -> None:
        card = self._card(310)
        card._last_card_wrap = 264

        card._rewrap()

        self.assertNotIn("wraplength", card.value_label.options)

    def test_card_rewrap_applies_growth_beyond_hysteresis(self) -> None:
        card = self._card(315)
        card._last_card_wrap = 264

        card._rewrap()

        self.assertEqual(card.value_label.options["wraplength"], 279)

    def test_card_rewrap_exact_fit_when_shrinking(self) -> None:
        card = self._card(290)
        card._last_card_wrap = 264

        card._rewrap()

        self.assertEqual(card.value_label.options["wraplength"], 254)

    def test_card_rewrap_never_clips_at_narrow_width(self) -> None:
        card = self._card(50)

        card._rewrap()

        self.assertEqual(card.value_label.options["wraplength"], 14)

    def test_card_rewrap_ignores_unmeasured_width(self) -> None:
        card = self._card(1)

        card._rewrap()

        self.assertNotIn("wraplength", card.value_label.options)


class MetricValueWrapTests(unittest.TestCase):
    def test_unsized_returns_zero(self) -> None:
        self.assertEqual(ui_layout.metric_value_wrap(0), 0)

    def test_reserves_label_space(self) -> None:
        self.assertEqual(ui_layout.metric_value_wrap(264), 134)

    def test_floor_applied_for_narrow_wraps(self) -> None:
        self.assertEqual(ui_layout.metric_value_wrap(120), 60)

    def test_custom_label_space(self) -> None:
        self.assertEqual(ui_layout.metric_value_wrap(264, label_space=100), 164)


class PendingTransitionTests(unittest.TestCase):
    class FakeScheduler:
        def __init__(self) -> None:
            self.scheduled: list[tuple[int, Any, str]] = []
            self.cancelled: list[str] = []
            self.next_id = 0

        def schedule(self, delay: int, callback: Any) -> str | None:
            self.next_id += 1
            ident = f"t{self.next_id}"
            self.scheduled.append((delay, callback, ident))
            return ident

        def cancel(self, ident: Any) -> bool:
            if ident is not None:
                self.cancelled.append(ident)
                self.scheduled = [
                    entry for entry in self.scheduled if entry[2] != ident
                ]
            return True

    def _make(self) -> tuple[PendingTransition, "PendingTransitionTests.FakeScheduler"]:
        scheduler = self.FakeScheduler()
        transition = PendingTransition(scheduler.schedule, scheduler.cancel)
        return transition, scheduler

    def test_applies_after_delay_exactly_once(self) -> None:
        transition, scheduler = self._make()
        apply = Mock()

        transition.start(500, apply)
        self.assertEqual(apply.call_count, 0)
        self.assertEqual(len(scheduler.scheduled), 1)

        scheduler.scheduled[0][1]()
        self.assertEqual(apply.call_count, 1)
        self.assertIsNone(transition.pending_id)

    def test_start_supersedes_previous_pending(self) -> None:
        transition, scheduler = self._make()
        apply = Mock()

        transition.start(500, apply)
        transition.start(500, apply)

        self.assertEqual(len(scheduler.cancelled), 1)
        self.assertEqual(len(scheduler.scheduled), 1)
        scheduler.scheduled[0][1]()
        self.assertEqual(apply.call_count, 1)

    def test_cancel_prevents_apply(self) -> None:
        transition, scheduler = self._make()
        apply = Mock()

        transition.start(500, apply)
        transition.cancel()

        self.assertEqual(len(scheduler.scheduled), 0)
        self.assertIsNone(transition.pending_id)
        self.assertEqual(apply.call_count, 0)

    def test_cancel_is_idempotent(self) -> None:
        transition, scheduler = self._make()

        transition.cancel()
        transition.cancel()

        self.assertEqual(scheduler.cancelled, [])
        self.assertIsNone(transition.pending_id)

    def test_schedule_returning_none_is_safe(self) -> None:
        class NoneScheduler:
            def __init__(self) -> None:
                self.cancelled: list[str] = []

            def schedule(self, delay: int, callback: Any) -> str | None:
                del delay, callback
                return None

            def cancel(self, ident: Any) -> bool:
                if ident is not None:
                    self.cancelled.append(ident)
                return True

        scheduler = NoneScheduler()
        transition = PendingTransition(scheduler.schedule, scheduler.cancel)
        apply = Mock()

        transition.start(500, apply)
        self.assertIsNone(transition.pending_id)
        transition.start(500, apply)
        self.assertIsNone(transition.pending_id)

    def test_pending_id_tracks_current_timer(self) -> None:
        transition, _scheduler = self._make()

        transition.start(500, Mock())
        self.assertEqual(transition.pending_id, "t1")
        transition.start(500, Mock())
        self.assertEqual(transition.pending_id, "t2")


class DialogFooterGutterTests(unittest.TestCase):
    def test_status_label_is_guttered_from_action_buttons(self) -> None:
        footer = Mock()
        status = Mock()
        frame_factory = Mock(return_value=footer)
        label_factory = Mock(return_value=status)

        returned_footer, returned_status = ui_layout.dialog_footer(
            "container",
            frame_cls=frame_factory,
            label_cls=label_factory,
            colors={"background": "#fff", "secondary": "#666"},
            status_text="Ready",
        )

        self.assertIs(returned_footer, footer)
        self.assertIs(returned_status, status)
        footer.pack.assert_called_once_with(fill="x", pady=(14, 0))
        status.pack.assert_called_once_with(
            side="left",
            padx=(0, ui_layout.FOOTER_GUTTER),
        )


class DialogShellPrimitiveTests(unittest.TestCase):
    class FakeToplevel:
        def __init__(self) -> None:
            self.calls: dict[str, Any] = {}

        def title(self, text: str) -> None:
            self.calls["title"] = text

        def geometry(self, size: str) -> None:
            self.calls["geometry"] = size

        def minsize(self, *size: int) -> None:
            self.calls["minsize"] = size

        def configure(self, **options: Any) -> None:
            self.calls["configure"] = options

        def transient(self, master: Any) -> None:
            self.calls["transient"] = master

        def protocol(self, name: str, command: Any) -> None:
            self.calls["protocol"] = (name, command)

    def test_dialog_shell_configures_window_and_container(self) -> None:
        container = Mock()
        frame_factory = Mock(return_value=container)
        toplevel = self.FakeToplevel()
        close = lambda: None

        result = ui_layout.dialog_shell(
            toplevel,
            master="root",
            title="CPU Processes",
            geometry="900x560",
            minsize=(760, 480),
            colors={"background": "#fff"},
            padx=24,
            pady=22,
            frame_cls=frame_factory,
            on_close=close,
        )

        self.assertIs(result, container)
        self.assertEqual(toplevel.calls["title"], "CPU Processes")
        self.assertEqual(toplevel.calls["geometry"], "900x560")
        self.assertEqual(toplevel.calls["minsize"], (760, 480))
        self.assertEqual(toplevel.calls["configure"], {"bg": "#fff"})
        self.assertEqual(toplevel.calls["transient"], "root")
        self.assertEqual(toplevel.calls["protocol"][1], close)
        frame_factory.assert_called_once_with(
            toplevel,
            bg="#fff",
            padx=24,
            pady=22,
        )
        container.pack.assert_called_once_with(fill="both", expand=True)

    def test_dialog_shell_omits_close_protocol_when_not_requested(self) -> None:
        frame_factory = Mock(return_value=Mock())
        toplevel = self.FakeToplevel()

        ui_layout.dialog_shell(
            toplevel,
            master="root",
            title="T",
            geometry="1x1",
            minsize=(100, 100),
            colors={"background": "#fff"},
            padx=10,
            pady=10,
            frame_cls=frame_factory,
        )

        self.assertNotIn("protocol", toplevel.calls)

    def test_action_buttons_pack_right_in_given_order(self) -> None:
        class FakeButton:
            instances: ClassVar[list["FakeButton"]] = []

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.kwargs = kwargs
                self.pack_kwargs: dict[str, Any] = {}
                FakeButton.instances.append(self)

            def pack(self, **options: Any) -> None:
                self.pack_kwargs = options

        FakeButton.instances = []
        refresh = lambda: None
        quit_action = lambda: None

        created = ui_layout.pack_action_buttons(
            "footer",
            [
                ("Refresh", refresh, None, (8, 0)),
                ("Quit Selected", quit_action, "Danger.TButton", None),
            ],
            button_cls=FakeButton,
        )

        self.assertEqual(len(created), 2)
        first, second = FakeButton.instances
        self.assertEqual(first.kwargs["text"], "Refresh")
        self.assertEqual(first.pack_kwargs, {"side": "right", "padx": (8, 0)})
        self.assertEqual(second.kwargs["text"], "Quit Selected")
        self.assertEqual(second.kwargs["style"], "Danger.TButton")
        self.assertEqual(second.pack_kwargs, {"side": "right"})


if __name__ == "__main__":
    unittest.main()
