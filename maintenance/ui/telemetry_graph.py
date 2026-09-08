"""Small live telemetry graph primitives for detail surfaces."""

from __future__ import annotations

import tkinter as tk
from math import isfinite
from typing import Any

from maintenance.components.temperature import (
    TemperatureSeriesSnapshot,
    TemperatureState,
)
from maintenance.ui import styles as ui_styles


class TelemetryMiniGraph(tk.Frame):
    """A tiny stable Canvas graph for one thermal series."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        colors: dict[str, str],
        title: str,
        height: int = 108,
        width: int = 520,
        canvas_cls: type[tk.Canvas] = tk.Canvas,
        label_cls: type[tk.Label] = tk.Label,
    ) -> None:
        super().__init__(master, bg=colors["card"])
        self.colors = colors
        self.title = title
        self._snapshot: TemperatureSeriesSnapshot | None = None
        self._height = height
        self._width = width
        self._title_label = label_cls(
            self,
            text=title,
            bg=colors["card"],
            fg=colors["text"],
            font=ui_styles.FONTS["detail_section"],
            anchor="w",
        )
        self._title_label.pack(anchor="w")
        self._state_label = label_cls(
            self,
            text="",
            bg=colors["card"],
            fg=colors["secondary"],
            font=ui_styles.FONTS["body"],
            anchor="w",
        )
        self._state_label.pack(anchor="w", pady=(2, 4))
        self._canvas = canvas_cls(
            self,
            bg=colors["card"],
            highlightthickness=0,
            height=height,
            width=width,
        )
        self._canvas.pack(fill="x", expand=False)
        self._canvas.bind("<Configure>", self._redraw)
        self.bind("<Configure>", self._redraw)

    @property
    def snapshot(self) -> TemperatureSeriesSnapshot | None:
        return self._snapshot

    def render(self, snapshot: TemperatureSeriesSnapshot | None) -> None:
        self._snapshot = snapshot
        self._redraw()

    def _redraw(self, _event: Any = None) -> None:
        canvas = self._canvas
        try:
            width = max(int(canvas.winfo_width()), self._width)
            height = max(int(canvas.winfo_height()), self._height)
        except tk.TclError:
            return
        canvas.delete("all")
        snapshot = self._snapshot
        if snapshot is None:
            self._draw_empty(canvas, width, height, "No temperature data")
            return

        state_text = snapshot.state.value.replace("_", " ").title()
        current = snapshot.current_celsius
        minimum = snapshot.minimum_celsius
        maximum = snapshot.maximum_celsius
        if current is not None:
            state_text = f"{state_text} • {current:.0f}°C"
        self._state_label.config(text=state_text)

        if snapshot.state is TemperatureState.UNSUPPORTED:
            self._draw_empty(canvas, width, height, "Temperature not supported")
            return
        if snapshot.state is TemperatureState.ERROR:
            self._draw_empty(
                canvas, width, height, "Temperature temporarily unavailable"
            )
            return
        if snapshot.state is TemperatureState.NO_DATA or not snapshot.samples:
            self._draw_empty(canvas, width, height, "Waiting for the first sample")
            return

        values = [sample.value_celsius for sample in snapshot.samples]
        if not values:
            self._draw_empty(canvas, width, height, "No temperature data")
            return

        left = 14
        top = 14
        bottom = height - 18
        right = width - 14
        plot_height = max(bottom - top, 1)
        plot_width = max(right - left, 1)
        lowest = min(values)
        highest = max(values)
        if lowest == highest:
            lowest -= 1.0
            highest += 1.0

        warning = snapshot.warning_celsius
        critical = snapshot.critical_celsius
        if warning is not None:
            self._draw_threshold_line(
                canvas, left, right, top, bottom, warning, lowest, highest, "#f5a623"
            )
        if critical is not None:
            self._draw_threshold_line(
                canvas,
                left,
                right,
                top,
                bottom,
                critical,
                lowest,
                highest,
                self.colors["accent"],
            )

        points: list[float] = []
        count = len(values)
        for index, value in enumerate(values):
            x = left if count == 1 else left + (plot_width * index / (count - 1))
            y = bottom - ((value - lowest) / (highest - lowest) * plot_height)
            points.extend((x, y))
        if len(points) >= 4:
            canvas.create_line(
                *points, fill=self.colors["accent"], width=2, smooth=True
            )
        for x, y in zip(points[::2], points[1::2], strict=False):
            canvas.create_oval(
                x - 2, y - 2, x + 2, y + 2, fill=self.colors["accent"], outline=""
            )

        if current is not None and isfinite(current):
            canvas.create_text(
                left,
                2,
                text=f"Current {current:.0f}°C",
                anchor="nw",
                fill=self.colors["text"],
                font=ui_styles.FONTS["body"],
            )
        if minimum is not None and maximum is not None:
            canvas.create_text(
                right,
                2,
                text=f"Min {minimum:.0f}°C  Max {maximum:.0f}°C",
                anchor="ne",
                fill=self.colors["secondary"],
                font=ui_styles.FONTS["body"],
            )

    def _draw_empty(
        self, canvas: tk.Canvas, width: int, height: int, message: str
    ) -> None:
        self._state_label.config(text=message)
        canvas.create_rectangle(
            10, 10, width - 10, height - 12, outline=self.colors["border"]
        )
        canvas.create_text(
            width // 2,
            height // 2,
            text=message,
            fill=self.colors["secondary"],
            font=ui_styles.FONTS["body"],
        )

    @staticmethod
    def _draw_threshold_line(
        canvas: tk.Canvas,
        left: int,
        right: int,
        top: int,
        bottom: int,
        threshold: float,
        minimum: float,
        maximum: float,
        color: str,
    ) -> None:
        span = maximum - minimum
        if span <= 0:
            return
        y = bottom - ((threshold - minimum) / span * (bottom - top))
        canvas.create_line(left, y, right, y, fill=color, dash=(4, 4))
