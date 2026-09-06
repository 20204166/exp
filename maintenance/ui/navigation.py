"""Reusable in-window page routing for the System Analyzer UI.

Adapts two FastAPI principles without recreating any framework behaviour:

- *modular registration*: pages declare a named ``PageSpec`` and the app
  registers them once at its composition root, like including routers.
- *separation of page behaviour from app flow*: pages own their widgets and
  emit semantic callbacks; ``PageRouter`` only owns which frame is mapped.

The router extends the existing Tk switching behaviour (``pack_forget`` /
``pack``) rather than replacing it: every page is eagerly built once under a
stable host and only ever shown/hidden, so page state, widgets, scroll
positions and live Tk variables are preserved across navigation.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PageBuilder = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class PageSpec:
    """Declarative registration for one named page."""

    key: str
    build: PageBuilder


class PageRouter:
    """Register named pages once and switch between the retained frames.

    Accepts an optional app ``coordinator`` (the ``AppCoordinator`` shock
    absorber). Pages that need heavy data can ``register_loader`` a
    background task per page: ``refresh(key)`` then shows the last cached
    result instantly while a fresh run happens in the background, with
    duplicate triggers coalesced by the coordinator.
    """

    def __init__(self, host: Any, *, coordinator: Any = None) -> None:
        self._host = host
        self._coordinator = coordinator
        self._pages: dict[str, Any] = {}
        self._loaders: dict[str, tuple[Callable[[], Any], Callable[[Any], None]]] = {}
        self._active_key: str | None = None

    @property
    def host(self) -> Any:
        return self._host

    @property
    def active_key(self) -> str | None:
        return self._active_key

    @property
    def registered_keys(self) -> tuple[str, ...]:
        return tuple(self._pages)

    def register(self, spec: PageSpec) -> Any:
        """Build one page immediately and retain it without packing it.

        The builder runs exactly once, receives the router host as its
        parent, and must not pack the returned page root (the router owns
        page visibility).
        """

        if not spec.key:
            raise ValueError("Page key cannot be empty")
        if spec.key in self._pages:
            raise ValueError(f"Page already registered: {spec.key}")
        page = spec.build(self._host)
        self._pages[spec.key] = page
        return page

    def register_loader(
        self,
        key: str,
        loader: Callable[[], Any],
        on_result: Callable[[Any], None],
    ) -> None:
        """Attach a heavy-data loader to one page.

        When the app has provided a coordinator, ``refresh`` runs this loader
        through it (coalesced, cached, delivered on the UI thread) and feeds
        every result to ``on_result``.
        """

        if key not in self._pages:
            raise KeyError(f"Unknown page: {key}")
        self._loaders[key] = (loader, on_result)

    def refresh(self, key: str) -> int | None:
        """Redraw a page from its cached data and re-run it in the background.

        The last cached result (if any) is applied immediately through
        ``on_result``; a fresh loader run is then triggered through the
        coordinator and coalesced with any run already in flight. Returns the
        run generation, or ``None`` when no loader or coordinator is present
        or the trigger was coalesced.
        """

        entry = self._loaders.get(key)
        if entry is None or self._coordinator is None:
            return None
        loader, on_result = entry
        cached = self._coordinator.last_result(key)
        if cached is not None:
            on_result(cached)

        def task_factory(
            _cancel_event: Any,
            _progress: Any,
        ) -> Any:
            return loader()

        return self._coordinator.run(
            key,
            task_factory,
            on_result=lambda _key, result: on_result(result),
        )

    def show(self, key: str) -> Any:
        """Map the named page, hiding the current one.

        The destination is resolved and validated before anything is hidden,
        so an unknown key raises ``KeyError`` and leaves the current page
        mapped. If packing the destination fails the previous page is
        restored.
        """

        if key not in self._pages:
            raise KeyError(f"Unknown page: {key}")
        if key == self._active_key:
            return self._pages[key]

        destination = self._pages[key]
        previous_key = self._active_key
        previous_page = self._pages[previous_key] if previous_key is not None else None
        if previous_page is not None:
            previous_page.pack_forget()

        try:
            destination.pack(fill=tk.BOTH, expand=True)
        except Exception:
            if previous_page is not None:
                previous_page.pack(fill=tk.BOTH, expand=True)
            raise
        self._active_key = key
        return destination

    def get(self, key: str) -> Any:
        """Return a retained page frame, raising for an unknown key."""

        try:
            return self._pages[key]
        except KeyError as error:
            raise KeyError(f"Unknown page: {key}") from error

    def is_mapped(self, key: str) -> bool:
        return self._active_key == key
