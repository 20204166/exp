"""Focused tests for the reusable in-window page router."""

import unittest
from typing import Any
from unittest.mock import Mock

from tests.support.scheduling import DeferredRunner


class FakePage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.pack_calls: list[dict[str, Any]] = []
        self.pack_forget_calls = 0
        self._mapped = False

    def pack(self, **options: Any) -> None:
        self.pack_calls.append(options)
        self._mapped = True

    def pack_forget(self) -> None:
        self.pack_forget_calls += 1
        self._mapped = False

    @property
    def mapped(self) -> bool:
        return self._mapped


def make_router(*names: str) -> tuple[Any, dict[str, FakePage]]:
    from maintenance.ui.navigation import PageRouter, PageSpec

    host = Mock()
    pages: dict[str, FakePage] = {}

    def build(name: str):
        def builder(parent: Any) -> FakePage:
            page = FakePage(name)
            pages[name] = page
            return page

        return builder

    router = PageRouter(host)
    for name in names:
        router.register(PageSpec(name, build(name)))
    return router, pages


class PageRouterTests(unittest.TestCase):
    def test_builder_receives_host_exactly_once_without_packing(self) -> None:
        router, pages = make_router("a")
        page = pages["a"]

        self.assertEqual(page.pack_calls, [])
        self.assertEqual(page.pack_forget_calls, 0)
        self.assertIsNone(router.active_key)

    def test_register_rejects_empty_and_duplicate_keys(self) -> None:
        from maintenance.ui.navigation import PageRouter, PageSpec

        router = PageRouter(Mock())
        with self.assertRaises(ValueError):
            router.register(PageSpec("", lambda _parent: object()))
        router.register(PageSpec("a", lambda _parent: object()))
        with self.assertRaises(ValueError):
            router.register(PageSpec("a", lambda _parent: object()))

    def test_first_show_packs_destination_full(self) -> None:
        router, pages = make_router("a", "b")

        router.show("a")

        self.assertEqual(router.active_key, "a")
        self.assertTrue(pages["a"].mapped)
        self.assertFalse(pages["b"].mapped)
        self.assertEqual(
            pages["a"].pack_calls[-1],
            {"fill": "both", "expand": True},
        )

    def test_switch_hides_previous_and_shows_retained_target(self) -> None:
        router, pages = make_router("a", "b")
        router.show("a")

        router.show("b")

        self.assertEqual(router.active_key, "b")
        self.assertEqual(pages["a"].pack_forget_calls, 1)
        self.assertFalse(pages["a"].mapped)
        self.assertTrue(pages["b"].mapped)

    def test_return_uses_identical_frame_object(self) -> None:
        router, pages = make_router("a", "b")
        router.show("a")
        router.show("b")

        first = router.show("a")

        self.assertIs(first, pages["a"])
        self.assertEqual(pages["b"].pack_forget_calls, 1)
        self.assertEqual(pages["a"].pack_forget_calls, 1)

    def test_showing_active_page_is_a_noop(self) -> None:
        router, pages = make_router("a")
        router.show("a")

        returned = router.show("a")

        self.assertIs(returned, pages["a"])
        self.assertEqual(len(pages["a"].pack_calls), 1)

    def test_unknown_key_raises_and_leaves_current_visible(self) -> None:
        router, pages = make_router("a")
        router.show("a")

        with self.assertRaises(KeyError):
            router.show("nope")

        self.assertEqual(router.active_key, "a")
        self.assertTrue(pages["a"].mapped)
        self.assertEqual(pages["a"].pack_forget_calls, 0)

    def test_mapping_failure_restores_previous_page(self) -> None:
        from maintenance.ui.navigation import PageRouter, PageSpec

        host = Mock()

        class ExplodingPage(FakePage):
            def pack(self, **options: Any) -> None:
                raise RuntimeError("layout failed")

        pages: dict[str, Any] = {}
        router = PageRouter(host)
        pages["a"] = FakePage("a")
        router.register(PageSpec("a", lambda _parent: pages["a"]))
        router.register(
            PageSpec(
                "b",
                lambda _parent: pages.setdefault(
                    "b",
                    ExplodingPage("b"),
                ),
            )
        )
        router.show("a")

        with self.assertRaises(RuntimeError):
            router.show("b")

        self.assertEqual(router.active_key, "a")
        self.assertEqual(pages["a"].pack_forget_calls, 1)
        self.assertEqual(pages["a"].pack_calls[-1]["expand"], True)

    def test_active_key_updates_only_after_success(self) -> None:
        router, _pages = make_router("a")
        router.show("a")
        self.assertEqual(router.active_key, "a")

    def test_get_and_registered_keys(self) -> None:
        router, pages = make_router("a", "b")

        self.assertEqual(router.registered_keys, ("a", "b"))
        self.assertIs(router.get("a"), pages["a"])
        with self.assertRaises(KeyError):
            router.get("nope")

    def test_is_mapped_reflects_active_page(self) -> None:
        router, _pages = make_router("a", "b")
        self.assertFalse(router.is_mapped("a"))
        router.show("a")
        self.assertTrue(router.is_mapped("a"))
        self.assertFalse(router.is_mapped("b"))


class PageRouterLoaderTests(unittest.TestCase):
    def _router(self, coordinator: Any) -> Any:
        from maintenance.ui.navigation import PageRouter, PageSpec

        router = PageRouter(Mock(), coordinator=coordinator)
        page = Mock()
        router.register(PageSpec("data", lambda _parent: page))
        return router, page

    def test_refresh_without_loader_or_coordinator_is_a_noop(self) -> None:
        from maintenance.ui.navigation import PageRouter, PageSpec

        router = PageRouter(Mock())
        router.register(PageSpec("data", lambda _parent: Mock()))
        self.assertIsNone(router.refresh("data"))

    def test_refresh_shows_cached_result_instantly_then_reloads(self) -> None:
        from maintenance.components.coordinator import AppCoordinator

        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        coordinator.store("data", "cached")
        router, _page = self._router(coordinator)
        received: list[str] = []
        router.register_loader("data", lambda: "fresh", received.append)

        router.refresh("data")

        self.assertEqual(received, ["cached"])
        self.assertTrue(coordinator.in_flight("data"))
        runner.run_next()
        self.assertEqual(received, ["cached", "fresh"])
        self.assertEqual(coordinator.last_result("data"), "fresh")

    def test_refresh_coalesces_repeated_triggers(self) -> None:
        from maintenance.components.coordinator import AppCoordinator

        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        router, _page = self._router(coordinator)
        received: list[str] = []
        router.register_loader("data", lambda: "fresh", received.append)

        first = router.refresh("data")
        second = router.refresh("data")

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(runner.workers), 1)
        runner.run_next()
        runner.run_next()
        self.assertEqual(received, ["fresh", "fresh"])

    def test_register_loader_rejects_unknown_page(self) -> None:
        from maintenance.ui.navigation import PageRouter

        router = PageRouter(Mock(), coordinator=Mock())
        with self.assertRaises(KeyError):
            router.register_loader("nope", lambda: None, lambda _result: None)


if __name__ == "__main__":
    unittest.main()
