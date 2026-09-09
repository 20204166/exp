"""Pure dashboard card visibility and polling policy decisions."""

from __future__ import annotations

from collections.abc import Mapping

from maintenance.models import CapabilityState
from maintenance.preferences import AppPreferences


def is_card_visible(
    key: str,
    *,
    preferences: AppPreferences | None,
    capabilities: Mapping[str, CapabilityState],
) -> bool:
    """Return whether a card should be rendered for the current preferences."""

    if preferences is None:
        return True
    if key not in preferences.visible_cards:
        return False
    if not preferences.hide_unavailable_cards:
        return True
    return capabilities.get(key, CapabilityState.UNKNOWN) != CapabilityState.UNSUPPORTED


def should_pause_polling(
    key: str,
    *,
    preferences: AppPreferences | None,
    capabilities: Mapping[str, CapabilityState],
) -> bool:
    """Return whether periodic polling for one component should pause."""

    manually_hidden = preferences is not None and key not in preferences.visible_cards
    auto_hidden = (
        preferences is not None
        and preferences.hide_unavailable_cards
        and capabilities.get(key, CapabilityState.UNKNOWN)
        == CapabilityState.UNSUPPORTED
    )
    if key in ("network", "battery"):
        return manually_hidden or auto_hidden
    if key == "gpu":
        return auto_hidden
    return False
