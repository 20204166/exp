"""Preference event and persistence adapters for ``AppWindow``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def apply_preferences(controller: Any, candidate: Any) -> None:
    window = _window_symbols()
    try:
        controller._preferences_store.save(candidate)
    except window.PreferencesSaveError as error:
        window.LOGGER.warning("Failed to save preferences: %s", error)
        controller.preferences_page.refresh_from(controller._preferences)
        controller.preferences_page.show_error("Preferences could not be saved")
        return
    controller._preferences = candidate
    controller._reconcile_intervals()
    controller._reconcile_cards_and_polling()
    controller._apply_appearance()
    controller.preferences_page.refresh_from(controller._preferences)
    controller.preferences_page.show_status("Preferences saved")


def try_apply_preference(controller: Any, builder: Callable[[], Any]) -> bool:
    try:
        candidate = builder()
    except ValueError as error:
        controller.preferences_page.refresh_from(controller._preferences)
        controller.preferences_page.show_error(str(error))
        return False
    apply_preferences(controller, candidate)
    return True


def on_interval_commit(controller: Any, key: str, seconds: int) -> None:
    try_apply_preference(
        controller, lambda: controller._preferences.with_interval(key, seconds * 1000)
    )


def on_card_visibility_change(controller: Any, key: str, visible: bool) -> None:
    applied = try_apply_preference(
        controller, lambda: controller._preferences.with_card_visibility(key, visible)
    )
    if applied and visible:
        controller._request_component_refresh(key)


def on_auto_hide_change(controller: Any, enabled: bool) -> None:
    apply_preferences(
        controller, controller._preferences.with_hide_unavailable_cards(enabled)
    )


def on_appearance_change(controller: Any, theme: str) -> None:
    try:
        candidate = controller._preferences.with_appearance(theme)
    except ValueError as error:
        controller.preferences_page.refresh_from(controller._preferences)
        controller.preferences_page.show_error(str(error))
        return
    apply_preferences(controller, candidate)


def on_reset(controller: Any) -> None:
    window = _window_symbols()
    if window.messagebox.askyesno(
        "Reset Preferences?",
        "Reset all preferences to their defaults?",
        parent=controller.master,
    ):
        apply_preferences(controller, window.AppPreferences.defaults())


def _window_symbols() -> Any:
    import window

    return window
