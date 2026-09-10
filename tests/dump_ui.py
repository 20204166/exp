"""Dump the rendered widget structure of the dashboard and each dialog.

Used to compare the before/after UI extraction: run this script with the
same interpreter in two working trees and diff the outputs. Only structural,
deterministic facts are emitted (widget class, key config values, geometry,
pack options, tree columns) so the comparison proves behaviour-preserving
layout, not pixel identity.
"""

import json
import tkinter as tk
from tkinter import ttk
from unittest.mock import Mock, patch

from maintenance import dialogs
from maintenance.models import CapabilityState
from tests.support.live_tk import TEST_COLORS, pump
from tests.support.models import make_summary
from tests.support.temperature import make_temperature_sample
from window import AppWindow


def cget_values(widget, options):
    result = {}
    for option in options:
        try:
            result[option] = widget.cget(option)
        except (tk.TclError, AttributeError):
            pass
    return result


def describe_widget(widget):
    try:
        klass = widget.winfo_class()
    except (tk.TclError, AttributeError):
        return None
    info = {"class": klass}
    try:
        info["pack"] = widget.pack_info()
    except (tk.TclError, AttributeError):
        pass
    if isinstance(widget, tk.Label):
        info["config"] = cget_values(
            widget, ("text", "font", "wraplength", "justify", "anchor")
        )
    elif isinstance(widget, ttk.Label):
        info["config"] = cget_values(widget, ("text", "style", "wraplength"))
    elif isinstance(widget, (tk.Button, ttk.Button)):
        info["config"] = cget_values(widget, ("text", "style", "state"))
    elif isinstance(widget, ttk.Progressbar):
        info["config"] = cget_values(widget, ("mode", "maximum", "value", "style"))
    elif isinstance(widget, ttk.Treeview):
        info["columns"] = widget.cget("columns")
    info["children"] = []
    try:
        children = widget.winfo_children()
    except (tk.TclError, AttributeError):
        children = []
    for child in children:
        described = describe_widget(child)
        if described is not None:
            info["children"].append(described)
    return info


def normalize_geometry(geometry):
    if "x" not in geometry:
        return geometry
    return geometry.split("+")[0]


def colors():
    return dict(TEST_COLORS)


def summary(key, title, details, value="", subtitle="subtitle", percent=None):
    return make_summary(
        key,
        title,
        value=value,
        subtitle=subtitle,
        percent=percent,
        details=details,
    )


def run(label, build):
    root = tk.Tk()
    try:
        extra = build(root) or {}
        record = {
            "label": label,
            "extra": extra,
            "root": describe_widget(root),
            "toplevels": [
                describe_widget(widget)
                for widget in root.winfo_children()
                if isinstance(widget, tk.Toplevel)
            ],
        }
        return record
    finally:
        try:
            root.destroy()
        except (tk.TclError, RuntimeError):
            pass


def build_window(root):
    window = AppWindow(master=root)
    for identifier in tuple(window._pending_after_ids):
        window._cancel_timer(identifier)
    pump(window.master)
    extra = {
        "geometry": normalize_geometry(window.master.geometry()),
        "minsize": window.master.minsize(),
        "pages": list(window._page_router.registered_keys),
        "active_page": window._page_router.active_key,
    }
    for page_key in window._page_router.registered_keys:
        extra[f"page.{page_key}.mapped"] = window._page_router.is_mapped(page_key)
    for feature in window._feature_catalog.all():
        card = window.cards[feature.key]
        extra[f"card.{feature.key}"] = {
            "title": card.title_label.cget("text"),
            "value": card.value_label.cget("text"),
            "action": card.details_label.cget("text"),
        }
    return extra


def build_settings_home(root):
    window = AppWindow(master=root)
    for identifier in tuple(window._pending_after_ids):
        window._cancel_timer(identifier)
    pump(window.master)
    window._show_settings_page()
    pump(window.master)
    home = window.settings_home
    extra = {
        "geometry": normalize_geometry(window.master.geometry()),
        "active_page": window._page_router.active_key,
        "mapped": {
            key: window._page_router.is_mapped(key)
            for key in window._page_router.registered_keys
        },
        "category_keys": list(home.category_keys),
        "back_button_text": home.back_button.cget("text"),
        "back_button_style": home.back_button.cget("style"),
        "category_button_styles": {
            key: home.category_button(key).cget("style") for key in home.category_keys
        },
    }
    return extra


def build_preferences(root):
    window = AppWindow(master=root)
    for identifier in tuple(window._pending_after_ids):
        window._cancel_timer(identifier)
    pump(window.master)
    window._show_settings_page()
    window._show_preferences_page()
    pump(window.master)
    page = window.preferences_page
    extra = {
        "geometry": normalize_geometry(window.master.geometry()),
        "active_page": window._page_router.active_key,
        "mapped": {
            key: window._page_router.is_mapped(key)
            for key in window._page_router.registered_keys
        },
        "interval_seconds": {
            key: var.get() for key, var in page._interval_vars.items()
        },
        "interval_bounds": {
            key: {
                "min": spec.minimum_seconds,
                "max": spec.maximum_seconds,
                "step": spec.step_seconds,
            }
            for key, spec in page._intervals.items()
        },
        "cards": {key: var.get() for key, var in page._card_vars.items()},
        "auto_hide": page._auto_hide_var.get(),
        "scan_status": page.manual_status_label.cget("text"),
        "scan_button_style": page.analyze_button.cget("style"),
        "cancel_button_style": page.cancel_button.cget("style"),
        "cancel_state": page.cancel_button.cget("state"),
        "back_button_text": page.back_button.cget("text"),
        "back_button_style": page.back_button.cget("style"),
        "reset_button_style": page.reset_button.cget("style"),
    }
    return extra


def build_thermals(root):
    window = AppWindow(master=root)
    for identifier in tuple(window._pending_after_ids):
        window._cancel_timer(identifier)
    context = window._selected_context()
    assert context is not None
    context.capabilities.update(
        {
            "cpu": CapabilityState.SUPPORTED,
            "gpu": CapabilityState.SUPPORTED,
            "storage": CapabilityState.SUPPORTED,
            "battery": CapabilityState.UNSUPPORTED,
        }
    )
    for component, value in (("cpu", 42.0), ("gpu", 44.0), ("storage", 38.0)):
        context.telemetry.record_summary(
            component,
            make_summary(
                component,
                component.upper(),
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample(component, value),),
            ),
        )
    window._show_thermals_page()
    pump(window.master)
    page = window.thermals_page
    return {
        "geometry": normalize_geometry(window.master.geometry()),
        "active_page": window._page_router.active_key,
        "mapped": {
            key: window._page_router.is_mapped(key)
            for key in window._page_router.registered_keys
        },
        "graph_components": list(page.graph_components),
        "back_button_text": page.back_button.cget("text"),
    }


def build_info(root, info_summary):
    dialog = dialogs.InfoDialog(root, summary=info_summary, colors=colors())
    pump(dialog)
    return {"geometry": normalize_geometry(dialog.geometry())}


def build_process(root, resource_key):
    manager = Mock()
    with patch.object(
        dialogs,
        "run_in_thread",
        side_effect=lambda *args, **kwargs: None,
    ):
        dialog = dialogs.ProcessDialog(
            root,
            analyzer=Mock(),
            manager=manager,
            resource_key=resource_key,
            colors=colors(),
            on_changed=lambda: None,
        )
    pump(dialog)
    extra = {
        "geometry": normalize_geometry(dialog.geometry()),
        "sort_default": [dialog._sort_column, dialog._sort_reverse],
    }
    if resource_key == "cpu":
        extra["columns"] = {
            column: dialog.tree.heading(column, "text")
            for column in dialog.tree.cget("columns")
        }
    return extra


def build_storage(root):
    with patch.object(
        dialogs,
        "run_in_thread",
        side_effect=lambda *args, **kwargs: None,
    ):
        dialog = dialogs.StorageDialog(
            root,
            analyzer=Mock(),
            manager=Mock(),
            colors=colors(),
            on_changed=lambda: None,
        )
    pump(dialog)
    return {
        "geometry": normalize_geometry(dialog.geometry()),
        "columns": {
            column: {
                "heading": dialog.tree.heading(column, "text"),
                "width": dialog.tree.column(column, "width"),
            }
            for column in dialog.tree.cget("columns")
        },
    }


def build_card(root, info_summary):
    frame = tk.Frame(root)
    frame.pack()
    card = dialogs.ResourceCard(
        frame,
        key=info_summary.key,
        title=info_summary.title,
        on_open=lambda _key: None,
        colors=colors(),
    )
    card.pack(fill="x")
    card.update_summary(info_summary)
    pump(root)
    return {
        "geometry": normalize_geometry(str(frame.winfo_width())),
        "title": card.title_label.cget("text"),
        "value": card.value_label.cget("text"),
        "action": card.details_label.cget("text"),
        "progress_style": (
            card.progress.cget("style") if card.progress is not None else None
        ),
    }


def main():
    records = [
        run("dashboard", build_window),
        run("settings", build_settings_home),
        run("preferences", build_preferences),
        run("thermals", build_thermals),
        run(
            "info-dialog-no-battery",
            lambda root: build_info(
                root,
                summary(
                    "battery",
                    "Battery",
                    (
                        "Battery information is unavailable.",
                        "CPU: 45°C",
                        "NVMe: 38°C",
                    ),
                    value="No battery",
                ),
            ),
        ),
        run(
            "info-dialog-long-gpu",
            lambda root: build_info(
                root,
                summary(
                    "gpu",
                    "GPU",
                    (
                        (
                            "Advanced Micro Devices, Inc. [AMD/ATI] Picasso "
                            "[Radeon Vega Series / Radeon Vega Mobile Series] "
                            "(rev da)"
                        ),
                        "GPU usage: 42%",
                        "Memory: 512.00 MiB used of 4.00 GiB",
                        "Temperature: 56°C",
                    ),
                    value="Radeon Vega Series",
                ),
            ),
        ),
        run("process-dialog-cpu", lambda root: build_process(root, "cpu")),
        run("process-dialog-memory", lambda root: build_process(root, "memory")),
        run("storage-dialog", build_storage),
        run(
            "card-long-values",
            lambda root: build_card(
                root,
                summary(
                    "gpu",
                    "GPU",
                    (
                        (
                            "Advanced Micro Devices, Inc. [AMD/ATI] Picasso "
                            "[Radeon Vega Series / Radeon Vega Mobile Series] "
                            "(rev da)"
                        ),
                        "Temperature: 56°C",
                    ),
                    value=("AMD Radeon Vega Series / Radeon Vega Mobile Series"),
                    percent=42.0,
                ),
            ),
        ),
    ]
    print(json.dumps(records, indent=1, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
