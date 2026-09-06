"""Instance-owned recording fake widgets for headless UI page tests.

The Settings Home and Preferences page adapters are dependency-injected, so
tests can substitute a recording fake Tk widget that captures constructor
options, config changes, bindings and pack calls. One fresh recorder is used
per test so its mutable registry never leaks between tests.
"""

from typing import Any


class FakeVar:
    """Minimal recording fake for a ``tk.StringVar``/``BooleanVar``."""

    def __init__(self, value: Any = False) -> None:
        self._value = value

    def set(self, value: Any) -> None:
        self._value = value

    def get(self) -> Any:
        return self._value

    def trace_add(self, *_args: Any) -> None:
        return None

    def trace_remove(self, *_args: Any) -> None:
        return None


class RecordingWidget:
    """Fake Tk widget that records construction and layout interactions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.kind: str | None = None
        self.pack_calls: list[dict[str, Any]] = []
        self.pack_forget_calls = 0
        self.config_options: dict[str, Any] = {}
        self.bindings: dict[str, Any] = {}
        self.mapped = True
        self._yview_fraction: float | None = None

    def pack(self, **options: Any) -> None:
        self.pack_calls.append(options)

    def grid(self, **options: Any) -> None:
        del options

    def pack_forget(self) -> None:
        self.pack_forget_calls += 1
        self.mapped = False

    def config(self, **options: Any) -> None:
        self.config_options.update(options)

    def configure(self, **options: Any) -> None:
        self.config_options.update(options)

    def bind(self, sequence: str, handler: Any) -> None:
        self.bindings[sequence] = handler

    def focus_set(self) -> None:
        pass

    def winfo_width(self) -> int:
        return 300

    def winfo_height(self) -> int:
        return 400

    def winfo_reqheight(self) -> int:
        return 100

    def winfo_ismapped(self) -> bool:
        return self.mapped

    def create_window(self, *args: Any, **kwargs: Any) -> int:
        return 1

    def itemconfigure(self, *args: Any, **kwargs: Any) -> None:
        pass

    def bbox(self, *args: Any) -> tuple[int, int, int, int]:
        return (0, 0, 100, 100)

    def winfo_children(self) -> list[Any]:
        return []

    def destroy(self) -> None:
        return None

    def yview(self, *args: Any) -> None:
        pass

    def yview_moveto(self, fraction: float) -> None:
        self._yview_fraction = fraction

    def set(self, *args: Any) -> None:
        pass

    def cget(self, name: str) -> Any:
        return self.kwargs.get(name, self.config_options.get(name))


class WidgetRecorder:
    """Builds and tracks fresh recording widgets by kind, owned by one test."""

    def __init__(self) -> None:
        self._widgets: list[RecordingWidget] = []

    def _make(self, kind: str) -> Any:
        def factory(*args: Any, **kwargs: Any) -> RecordingWidget:
            widget = RecordingWidget(*args, **kwargs)
            widget.kind = kind
            self._widgets.append(widget)
            return widget

        return factory

    def parent(self) -> RecordingWidget:
        widget = RecordingWidget()
        widget.kind = "parent"
        return widget

    def frame_cls(self) -> Any:
        return self._make("frame")

    def label_cls(self) -> Any:
        return self._make("label")

    def style_frame_cls(self) -> Any:
        return self._make("style_frame")

    def style_label_cls(self) -> Any:
        return self._make("style_label")

    def button_cls(self) -> Any:
        return self._make("button")

    def canvas_cls(self) -> Any:
        return self._make("canvas")

    def scrollbar_cls(self) -> Any:
        return self._make("scrollbar")

    def spinbox_cls(self) -> Any:
        return self._make("spinbox")

    def checkbutton_cls(self) -> Any:
        return self._make("checkbutton")

    def combobox_cls(self) -> Any:
        return self._make("combobox")

    def entry_cls(self) -> Any:
        return self._make("entry")

    def progressbar_cls(self) -> Any:
        return self._make("progressbar")

    def widgets(self, kind: str) -> list[RecordingWidget]:
        return [widget for widget in self._widgets if widget.kind == kind]

    def label_texts(
        self, kinds: tuple[str, ...] = ("label", "style_label")
    ) -> set[str]:
        texts: set[str] = set()
        for widget in self._widgets:
            if widget.kind in kinds:
                text = widget.kwargs.get("text")
                if isinstance(text, str):
                    texts.add(text)
        return texts

    def label_with_text(self, text: str) -> RecordingWidget:
        return next(
            widget
            for widget in self.widgets("label")
            if widget.kwargs.get("text") == text
        )
