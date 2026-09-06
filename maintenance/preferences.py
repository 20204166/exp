"""Central user preferences for the System Analyzer application.

This module owns the single preferences model and its JSON persistence. It
imports no Tkinter, scanner, UI, or window code, so it stays safe to load in
any interpreter and inside tests without a display.

- ``AppPreferences`` is a deeply immutable model whose defaults derive from
  the existing ``RefreshIntervals`` component defaults rather than duplicating
  them.
- ``PreferencesStore`` loads safely (malformed files fall back to defaults,
  never failing startup) and saves atomically (temporary file + ``os.replace``
  + best-effort directory fsync).
"""

import contextlib
import json
import logging
import os
import platform
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from maintenance.components.catalog import ResourceFeatureCatalog
from maintenance.components.coordinator import RefreshIntervals

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "system-analyzer"
CONFIG_FILE_NAME = "preferences.json"

_CARD_KEYS: tuple[str, ...] = tuple(
    feature.key for feature in ResourceFeatureCatalog().all()
)


@dataclass(frozen=True, slots=True)
class IntervalPolicy:
    """Valid range and stepping for one configurable refresh interval.

    Stored in milliseconds; the Settings UI renders whole seconds.
    """

    key: str
    minimum_ms: int
    maximum_ms: int
    step_ms: int


INTERVAL_POLICIES: dict[str, IntervalPolicy] = {
    "cpu": IntervalPolicy("cpu", 1000, 60_000, 1000),
    "network": IntervalPolicy("network", 1000, 60_000, 1000),
    "memory": IntervalPolicy("memory", 2000, 300_000, 1000),
    "gpu": IntervalPolicy("gpu", 3000, 300_000, 1000),
    "storage": IntervalPolicy("storage", 15_000, 600_000, 5000),
    "battery": IntervalPolicy("battery", 10_000, 600_000, 5000),
}


def validate_interval_ms(key: str, value: Any) -> bool:
    """Return whether ``value`` is a safe, policy-conforming interval.

    Booleans are rejected (they are ``int`` instances) and values must be
    positive whole seconds within the component-specific range and stepping.
    """

    policy = INTERVAL_POLICIES.get(key)
    if policy is None:
        return False
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    if value < policy.minimum_ms or value > policy.maximum_ms:
        return False
    return value % policy.step_ms == 0


def validate_card_key(key: Any) -> bool:
    return isinstance(key, str) and key in _CARD_KEYS


@dataclass(frozen=True, slots=True)
class AppPreferences:
    """Deeply immutable user preferences.

    ``visible_cards`` is a frozenset so the model stays hashable and truly
    immutable. Defaults are derived from ``RefreshIntervals`` and the feature
    catalog rather than copied into this module.
    """

    refresh_intervals: RefreshIntervals
    visible_cards: frozenset[str]
    hide_unavailable_cards: bool

    @classmethod
    def defaults(cls) -> "AppPreferences":
        intervals = RefreshIntervals()
        return cls(
            refresh_intervals=intervals,
            visible_cards=frozenset(intervals.as_dict()),
            hide_unavailable_cards=False,
        )

    def with_interval(self, key: str, milliseconds: int) -> "AppPreferences":
        """Return a copy with one component interval changed and validated."""

        current = self.refresh_intervals.as_dict()
        if key not in current:
            raise ValueError(f"Unknown component: {key}")
        if not validate_interval_ms(key, milliseconds):
            policy = INTERVAL_POLICIES[key]
            raise ValueError(
                f"{key} interval must be between {policy.minimum_ms // 1000} "
                f"and {policy.maximum_ms // 1000} seconds in whole steps"
            )
        updated = dict(current)
        updated[key] = milliseconds
        return replace(self, refresh_intervals=RefreshIntervals(**updated))

    def with_card_visibility(self, key: str, visible: bool) -> "AppPreferences":
        """Return a copy with one card's manual visibility changed."""

        if not validate_card_key(key):
            raise ValueError(f"Unknown card: {key}")
        updated = set(self.visible_cards)
        if visible:
            updated.add(key)
        else:
            updated.discard(key)
        return replace(self, visible_cards=frozenset(updated))

    def with_hide_unavailable_cards(self, enabled: bool) -> "AppPreferences":
        """Return a copy with automatic unavailable-card hiding changed."""

        if not isinstance(enabled, bool):
            raise TypeError("hide_unavailable_cards must be a boolean")
        return replace(self, hide_unavailable_cards=enabled)


def default_preferences_path(
    *,
    environment: dict[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Return the standard per-user preferences file for the active platform.

    Uses the same ``system-analyzer`` slug as the log directory but a
    configuration path, per the platform conventions (XDG_CONFIG_HOME on
    Linux, Application Support on macOS, APPDATA on Windows). All inputs are
    injectable so tests can be deterministic.
    """

    env = os.environ if environment is None else environment
    home_dir = Path.home() if home is None else home
    system = platform.system() if platform_name is None else platform_name

    if system == "Windows":
        appdata = env.get("APPDATA")
        if appdata:
            return Path(appdata) / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        return home_dir / "AppData" / "Roaming" / CONFIG_DIR_NAME / CONFIG_FILE_NAME
    if system == "Darwin":
        return (
            home_dir
            / "Library"
            / "Application Support"
            / CONFIG_DIR_NAME
            / CONFIG_FILE_NAME
        )
    xdg = env.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / CONFIG_DIR_NAME / CONFIG_FILE_NAME
    return home_dir / ".config" / CONFIG_DIR_NAME / CONFIG_FILE_NAME


class PreferencesSaveError(RuntimeError):
    """Raised when preferences could not be committed to disk."""


class PreferencesStore:
    """Load and atomically save an ``AppPreferences`` document.

    ``load()`` always returns valid preferences; malformed documents fall
    back to defaults (logged) and are never allowed to block startup. A later
    successful edit or reset replaces them.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> AppPreferences:
        text = self._read_raw()
        if text is None:
            return AppPreferences.defaults()
        return self._parse(text)

    def save(self, preferences: AppPreferences) -> None:
        """Validate and persist ``preferences`` atomically.

        A uniquely named temporary file is written in the destination
        directory, flushed and fsynced, then committed with ``os.replace``.
        Runtime state must only be published by the caller after this returns.
        """

        payload = self._serialize(preferences)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PreferencesSaveError(
                f"Cannot create preferences directory: {error}"
            ) from error

        temp_name: str | None = None
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=".preferences-",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            try:
                handle = os.fdopen(fd, "w", encoding="utf-8")
            except OSError:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise
            try:
                with handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
                temp_name = None
            finally:
                if temp_name is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(temp_name)
        except OSError as error:
            raise PreferencesSaveError(
                f"Failed to save preferences: {error}"
            ) from error

        self._fsync_directory()

    def reset_to_defaults(self) -> AppPreferences:
        """Persist and return the default preferences."""

        defaults = AppPreferences.defaults()
        self.save(defaults)
        return defaults

    def _read_raw(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            LOGGER.warning("Failed to read preferences: %s", error)
            return None

    def _parse(self, text: str) -> AppPreferences:
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            LOGGER.warning("Malformed preferences JSON; using defaults")
            return AppPreferences.defaults()
        if not isinstance(data, dict):
            LOGGER.warning("Preferences root must be an object; using defaults")
            return AppPreferences.defaults()
        if data.get("schema_version") != SCHEMA_VERSION:
            LOGGER.warning("Unsupported preferences schema; using defaults")
            return AppPreferences.defaults()

        intervals_data = data.get("refresh_intervals_ms")
        visible_data = data.get("visible_cards")
        hide_data = data.get("hide_unavailable_cards")
        if not isinstance(intervals_data, dict):
            LOGGER.warning("Preferences intervals are malformed; using defaults")
            return AppPreferences.defaults()

        expected_keys = RefreshIntervals().as_dict()
        parsed_intervals: dict[str, int] = {}
        for key in expected_keys:
            value = intervals_data.get(key)
            if not validate_interval_ms(key, value):
                LOGGER.warning(
                    "Preferences interval %r is invalid; using defaults", key
                )
                return AppPreferences.defaults()
            parsed_intervals[key] = cast(int, value)
        unknown_intervals = set(intervals_data) - set(expected_keys)
        if unknown_intervals:
            LOGGER.warning(
                "Preferences contain unknown intervals %s; using defaults",
                sorted(unknown_intervals),
            )
            return AppPreferences.defaults()

        if not isinstance(visible_data, list):
            LOGGER.warning("Preferences cards are malformed; using defaults")
            return AppPreferences.defaults()
        if not all(validate_card_key(key) for key in visible_data):
            LOGGER.warning("Preferences contain an unknown card; using defaults")
            return AppPreferences.defaults()
        if len(set(visible_data)) != len(visible_data):
            LOGGER.warning("Preferences cards contain duplicates; using defaults")
            return AppPreferences.defaults()
        if not isinstance(hide_data, bool):
            LOGGER.warning("Preferences hide flag is malformed; using defaults")
            return AppPreferences.defaults()

        return AppPreferences(
            refresh_intervals=RefreshIntervals(**parsed_intervals),
            visible_cards=frozenset(visible_data),
            hide_unavailable_cards=hide_data,
        )

    @staticmethod
    def _serialize(preferences: AppPreferences) -> str:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "refresh_intervals_ms": preferences.refresh_intervals.as_dict(),
            "visible_cards": sorted(preferences.visible_cards),
            "hide_unavailable_cards": preferences.hide_unavailable_cards,
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def _fsync_directory(self) -> None:
        """Best-effort fsync of the destination directory after replace.

        A failure here happens after the commit point, so it must never
        cause the caller to roll runtime state back to the old value.
        """

        if not hasattr(os, "O_DIRECTORY"):
            return
        try:
            dir_fd = os.open(
                self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            LOGGER.warning(
                "Preferences committed but directory fsync failed: %s",
                self.path.parent,
            )
        finally:
            with contextlib.suppress(OSError):
                os.close(dir_fd)
