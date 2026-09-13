"""Structural checks that every page follows the same wiring conventions.

This exists because of a real gap: ``ThermalsPage`` shipped a content button
(a Help cross-link) with no way to register it with ``ButtonCoordinator`` at
all -- the class simply never accepted the parameter, so nothing could have
wired it correctly even by accident. That class of bug is invisible until
someone tries to invoke the button by stable action ID and it silently isn't
there.

These tests catch it earlier and name exactly what is missing and where to
fix it:

1. Every page in ``_PAGE_REGISTRY`` that is expected to support
   ``ButtonCoordinator`` actually accepts the parameter (a structural check
   on the class itself).
2. Every such page's builder function in ``window_pages.py`` actually passes
   ``button_coordinator=`` through when constructing it (a builder can accept
   the parameter and still forget to use it -- this is a separate failure
   mode from #1 and needs its own check).
3. Every page falls back to the shared ``ui_styles.COLORS``/``ui_styles.FONTS``
   system rather than a disconnected copy.
4. (Behavioural, real Tk) A fully constructed ``AppWindow`` actually
   registers every expected page with the page router and every expected
   button with the button coordinator -- the end-to-end version of 1-2.
5. The scan-backed dialogs (``ProcessDialog``, ``StorageDialog``) accept and
   are actually passed the shared ``AppCoordinator`` -- the same #1/#2 check,
   applied to the one other ownership boundary in the app (background scan
   work), not just pages and buttons.

Adding a new page means adding one entry to ``_PAGE_REGISTRY`` below.
``dashboard_page.py`` is deliberately out of scope: it is a function-based
card builder, not a reusable Page class with the callbacks/colors/fonts
constructor shape every other page shares.

Ownership summary this file enforces end to end:
- **UICoordinator** (``maintenance/ui/render_coordinator.py``) owns page/
  component *visibility* -- checked by ``ScannerCatalogWiringTests`` and
  ``LiveWindowWiringTests.test_every_catalog_component_is_visible_on_the_dashboard``.
- **ButtonCoordinator** (``maintenance/ui/action_coordinator.py``) owns every
  button's stable action id, except each page's own page-level back button
  (an established, verified exception -- see ``_PAGE_REGISTRY``'s
  ``reason_if_not`` entries) -- checked by
  ``PageButtonCoordinatorWiringTests`` and
  ``LiveWindowWiringTests.test_every_expected_button_action_is_registered``.
- **AppCoordinator** (``maintenance/components/coordinator.py``) owns
  coalesced/cached/cancellable background work -- component scans, page data
  loads, and the two scan-backed dialogs -- and delivers every result back
  onto the UI thread -- checked by ``DialogAppCoordinatorWiringTests``.
  (``BackgroundTaskRunner``/``run_in_thread`` in ``maintenance/dialogs.py``
  is a deliberately separate mechanism for one-shot cancellable dialog
  actions such as delete/kill, not a bypass of this boundary.)
"""

from __future__ import annotations

import ast
import inspect
import tempfile
import textwrap
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maintenance.components.catalog import ResourceFeatureCatalog
from maintenance.dialogs import ProcessDialog, StorageDialog
from maintenance.scanner import SystemScanner
from maintenance.ui import window_lifecycle as ui_window_lifecycle
from maintenance.ui import window_pages as ui_window_pages
from maintenance.ui import window_presentation as ui_window_presentation
from maintenance.ui.cluster_page import ClusterPage
from maintenance.ui.diagnostics_page import DiagnosticsPage
from maintenance.ui.help_page import HelpPage, HelpTopicPage
from maintenance.ui.nodes_connections import NodesConnectionsPage
from maintenance.ui.preferences_page import PreferencesPage
from maintenance.ui.settings_home import SettingsHome
from maintenance.ui.thermals_page import ThermalsPage
from tests.support.live_tk import DISPLAY_AVAILABLE


@dataclass(frozen=True, slots=True)
class _PageWiring:
    name: str
    page_class: type
    builder: Any
    supports_button_coordinator: bool
    reason_if_not: str = ""


_PAGE_REGISTRY: tuple[_PageWiring, ...] = (
    _PageWiring(
        "Settings hub", SettingsHome, ui_window_pages.build_settings_home, True
    ),
    _PageWiring(
        "Preferences", PreferencesPage, ui_window_pages.build_preferences, True
    ),
    _PageWiring(
        "Nodes & Connections", NodesConnectionsPage, ui_window_pages.build_nodes, True
    ),
    _PageWiring(
        "All Systems (cluster)", ClusterPage, ui_window_pages.build_cluster, True
    ),
    _PageWiring("Thermals", ThermalsPage, ui_window_pages.build_thermals, True),
    _PageWiring(
        "Diagnostics", DiagnosticsPage, ui_window_pages.build_diagnostics, True
    ),
    _PageWiring("Help & Guide hub", HelpPage, ui_window_pages.build_help, True),
    _PageWiring(
        "Help topic detail",
        HelpTopicPage,
        ui_window_pages.build_help_topic,
        False,
        reason_if_not=(
            "has only a page-level back button; verified against every other "
            "page's source that none of them register their own back button "
            "with ButtonCoordinator either (SettingsHome, PreferencesPage, "
            "NodesConnectionsPage, ClusterPage, ThermalsPage, DiagnosticsPage, "
            "HelpPage all leave back_button unregistered), so there is "
            "nothing here that would need one"
        ),
    ),
)


def _constructor_call_passes_keyword(
    builder: Any, class_name: str, keyword: str
) -> bool:
    """Does ``builder``'s source construct ``class_name`` with ``keyword=``?

    Parses the builder function's own source with ``ast`` rather than
    substring-matching, so a keyword mentioned only in a comment or an
    unrelated call cannot produce a false pass.
    """

    source = textwrap.dedent(inspect.getsource(builder))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called_name = (
            func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        )
        if called_name != class_name:
            continue
        if any(kw.arg == keyword for kw in node.keywords):
            return True
    return False


class PageButtonCoordinatorWiringTests(unittest.TestCase):
    """Static checks: does the class support it, does the builder use it?"""

    def test_expected_pages_accept_button_coordinator(self) -> None:
        failures = []
        for entry in _PAGE_REGISTRY:
            if not entry.supports_button_coordinator:
                continue
            params = inspect.signature(entry.page_class).parameters
            if "button_coordinator" not in params:
                failures.append(
                    f"{entry.name} ({entry.page_class.__module__}."
                    f"{entry.page_class.__name__}) does not accept a "
                    "button_coordinator parameter -- add "
                    "`button_coordinator: ButtonCoordinator | None = None` to "
                    f"its __init__ and store it as self._button_coordinator."
                )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_expected_pages_are_actually_passed_a_button_coordinator(self) -> None:
        failures = []
        for entry in _PAGE_REGISTRY:
            if not entry.supports_button_coordinator:
                continue
            if not _constructor_call_passes_keyword(
                entry.builder, entry.page_class.__name__, "button_coordinator"
            ):
                failures.append(
                    f"{entry.name}: {entry.builder.__name__}() in "
                    "maintenance/ui/window_pages.py constructs "
                    f"{entry.page_class.__name__}(...) without passing "
                    "button_coordinator=controller._button_coordinator -- add "
                    "that keyword argument to the call."
                )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_exempt_pages_have_a_documented_reason(self) -> None:
        for entry in _PAGE_REGISTRY:
            if not entry.supports_button_coordinator:
                self.assertTrue(
                    entry.reason_if_not,
                    f"{entry.name} is marked exempt from button_coordinator "
                    "support but has no documented reason -- either add one "
                    "or give the class button_coordinator support.",
                )


class PageStyleFallbackTests(unittest.TestCase):
    """Every page must fall back to the shared style system, not a copy."""

    def test_pages_fall_back_to_shared_colors_and_fonts(self) -> None:
        failures = []
        for entry in _PAGE_REGISTRY:
            source = inspect.getsource(entry.page_class)
            if "ui_styles.COLORS" not in source:
                failures.append(
                    f"{entry.name} ({entry.page_class.__name__}.__init__) "
                    "does not reference ui_styles.COLORS -- its colours are "
                    "disconnected from the shared theme system."
                )
            if "ui_styles.FONTS" not in source:
                failures.append(
                    f"{entry.name} ({entry.page_class.__name__}.__init__) "
                    "does not reference ui_styles.FONTS -- its fonts are "
                    "disconnected from the shared theme system."
                )
        self.assertEqual(failures, [], "\n".join(failures))


@dataclass(frozen=True, slots=True)
class _DialogWiring:
    name: str
    dialog_class: type
    opener: Any


_DIALOG_REGISTRY: tuple[_DialogWiring, ...] = (
    _DialogWiring(
        "Process dialog", ProcessDialog, ui_window_presentation.open_resource
    ),
    _DialogWiring(
        "Storage dialog", StorageDialog, ui_window_presentation.open_resource
    ),
)


class DialogAppCoordinatorWiringTests(unittest.TestCase):
    """AppCoordinator is the shared shock-absorber for scan-backed dialogs.

    ``ProcessDialog``/``StorageDialog`` run coalesced, cached, cancellable
    scans through the app's one ``AppCoordinator`` -- the same instance the
    dashboard and pages use. Dropping ``coordinator=controller._coordinator``
    at the call site does not raise: the dialog silently falls back to a
    private ``_standalone_coordinator`` (see ``maintenance/dialogs.py``), so
    it still opens and still works, just decoupled from the app's shared
    cache/coalescing/cancel state -- a regression invisible without a
    dedicated check, same failure shape as the ButtonCoordinator gap this
    file was created to catch.
    """

    def test_expected_dialogs_accept_coordinator(self) -> None:
        failures = []
        for entry in _DIALOG_REGISTRY:
            params = inspect.signature(entry.dialog_class).parameters
            if "coordinator" not in params:
                failures.append(
                    f"{entry.name} ({entry.dialog_class.__module__}."
                    f"{entry.dialog_class.__name__}) does not accept a "
                    "coordinator parameter -- add "
                    "`coordinator: AppCoordinator | None = None` to its "
                    "__init__ and store it as self.coordinator."
                )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_expected_dialogs_are_actually_passed_a_coordinator(self) -> None:
        failures = []
        for entry in _DIALOG_REGISTRY:
            if not _constructor_call_passes_keyword(
                entry.opener, entry.dialog_class.__name__, "coordinator"
            ):
                failures.append(
                    f"{entry.name}: {entry.opener.__name__}() in "
                    "maintenance/ui/window_presentation.py constructs "
                    f"{entry.dialog_class.__name__}(...) without passing "
                    "coordinator=controller._coordinator -- add that "
                    "keyword argument to the call, or the dialog silently "
                    "falls back to a private, disconnected AppCoordinator."
                )
        self.assertEqual(failures, [], "\n".join(failures))


def _scan_component_dispatch_keys() -> set[str]:
    """The literal ``if key == "..."`` keys SystemScanner.scan_component handles.

    This is the one place in the dashboard pipeline that is NOT generically
    driven by ``ResourceFeatureCatalog`` -- everywhere else (card building,
    render-visibility, the Preferences visibility toggles) iterates
    ``feature_catalog.all()`` directly, so adding a catalog entry
    automatically wires those. The scanner dispatch has to be hand-written
    per key, which is exactly the kind of manual step that silently drifts.
    """

    source = textwrap.dedent(inspect.getsource(SystemScanner.scan_component))
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Name) and left.id == "key"):
            continue
        for op, comparator in zip(node.ops, node.comparators):
            if (
                isinstance(op, ast.Eq)
                and isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
            ):
                keys.add(comparator.value)
    return keys


class ScannerCatalogWiringTests(unittest.TestCase):
    """Catch a catalog entry and a scanner dispatch branch drifting apart.

    Card building, render-visibility (see the loop in window_lifecycle.py),
    and the Preferences card-visibility toggles are all already generic --
    they iterate ``ResourceFeatureCatalog.all()`` directly, so a new catalog
    entry reaches all three automatically. The scanner's dispatch is the one
    hand-written exception, and a catalog entry with no matching scanner
    branch (or vice versa) fails silently: a card that never gets real data,
    or scan logic nothing ever displays.
    """

    def test_catalog_keys_match_scanner_dispatch_keys(self) -> None:
        catalog_keys = {
            feature.key for feature in ResourceFeatureCatalog.DEFAULT_FEATURES
        }
        scanner_keys = _scan_component_dispatch_keys()

        catalog_only = catalog_keys - scanner_keys
        scanner_only = scanner_keys - catalog_keys
        failures = []
        if catalog_only:
            failures.append(
                f"In ResourceFeatureCatalog.DEFAULT_FEATURES but not handled by "
                f"SystemScanner.scan_component: {sorted(catalog_only)} -- add "
                'an `if key == "...":` branch there.'
            )
        if scanner_only:
            failures.append(
                f"Handled by SystemScanner.scan_component but not in "
                f"ResourceFeatureCatalog.DEFAULT_FEATURES: {sorted(scanner_only)} "
                "-- add a ResourceFeature entry, or the card, its render-"
                "visibility throttling, and its Preferences toggle will never "
                "exist."
            )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_render_visibility_is_driven_by_the_catalog_not_a_hardcoded_list(
        self,
    ) -> None:
        source = inspect.getsource(ui_window_lifecycle.sync_render_visibility)
        self.assertIn(
            "_feature_catalog.all()",
            source,
            "sync_render_visibility no longer iterates "
            "controller._feature_catalog.all() to set component visibility -- "
            "if it was changed to a fixed list, every future catalog entry "
            "will silently stop getting render-visibility throttling.",
        )


@unittest.skipUnless(DISPLAY_AVAILABLE, "no display for live Tk tests")
class LiveWindowWiringTests(unittest.TestCase):
    """End-to-end: build ONE real AppWindow and inspect everything it wired.

    This is the check that would have caught the original bug directly: a
    missing action ID here means a button a user can see does nothing when
    invoked through the coordinator, not just a missing constructor
    parameter. All three assertions share a single AppWindow/Tk root (real
    Tk construction/teardown is the expensive and, on this suite, somewhat
    flaky part -- see the module docstring in test_live_tk_resize.py) rather
    than each rebuilding one, which would triple the cost for no benefit.
    """

    root: Any
    window: Any
    _tempdir: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        import tkinter as tk
        from dataclasses import replace

        from maintenance.cluster import ClusterState, ClusterStore
        from maintenance.preferences import PreferencesStore
        from window import AppWindow

        super().setUpClass()
        cls.root = tk.Tk()
        cls._tempdir = tempfile.TemporaryDirectory()
        store = PreferencesStore(Path(cls._tempdir.name) / "preferences.json")
        # Discovery is irrelevant to page/button wiring; leaving it enabled
        # makes this test attempt real mDNS in a sandbox with no usable
        # multicast network, which fails but has been observed to leave the
        # process in a state where an unrelated later test's Tk teardown
        # aborts with "Tcl_AsyncDelete: async handler deleted by the wrong
        # thread". Disabling it removes that real-networking exposure from a
        # test that was never about discovery in the first place.
        cluster_store = ClusterStore(Path(cls._tempdir.name) / "cluster.json")
        cluster_store.save(
            replace(ClusterState.create_local(), discovery_enabled=False)
        )
        cls.window = AppWindow(
            master=cls.root, preferences_store=store, cluster_store=cluster_store
        )
        for identifier in tuple(cls.window._pending_after_ids):
            cls.window._cancel_timer(identifier)

    @classmethod
    def tearDownClass(cls) -> None:
        import tkinter as tk

        try:
            cls.window._close()
        except (tk.TclError, RuntimeError):
            pass
        try:
            cls.root.destroy()
        except (tk.TclError, RuntimeError):
            pass
        cls._tempdir.cleanup()
        super().tearDownClass()

    def test_every_expected_page_key_is_registered(self) -> None:
        from maintenance.ui.help_content import HELP_TOPICS

        expected = {
            "dashboard",
            "settings",
            "preferences",
            "nodes",
            "cluster",
            "thermals",
            "diagnostics",
            "help",
            *(f"help:{topic.key}" for topic in HELP_TOPICS),
        }
        registered = set(self.window._page_router.registered_keys)
        missing = expected - registered
        self.assertEqual(
            missing,
            set(),
            f"Pages missing from the page router: {sorted(missing)} -- "
            "register them with a PageSpec in window.py's _build_window.",
        )

    def test_every_expected_button_action_is_registered(self) -> None:
        from maintenance.ui.help_content import HELP_TOPICS

        coordinator = self.window._button_coordinator
        registered = set(coordinator.registered_ids())
        expected = {
            "settings:category:preferences",
            "settings:category:nodes",
            "settings:category:cluster",
            "settings:category:diagnostics",
            "settings:category:help",
            "thermals:learn-more",
            "nodes:learn-pairing",
            "diagnostics:copy",
            "preferences:full-system-scan",
            *(f"help:topic:{topic.key}" for topic in HELP_TOPICS),
        }
        missing = expected - registered
        self.assertEqual(
            missing,
            set(),
            f"Button actions never registered with the coordinator: "
            f"{sorted(missing)} -- trace the owning page's builder in "
            "window_pages.py and pass button_coordinator through.",
        )

    def test_every_catalog_component_is_visible_on_the_dashboard(self) -> None:
        render = self.window._render_coordinator()
        self.assertIsNotNone(render)
        assert render is not None
        missing = [
            feature.key
            for feature in self.window._feature_catalog.all()
            if not render._visible.get(f"component:{feature.key}")
        ]
        self.assertEqual(
            missing,
            [],
            f"Dashboard components never marked visible: {missing} -- "
            "sync_render_visibility (window_lifecycle.py) should have set "
            "component:<key> True for every feature_catalog entry once the "
            "dashboard page is active.",
        )


if __name__ == "__main__":
    unittest.main()
