"""Qt main-window host for retained Qt page widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from maintenance.ui.navigation import PageRouter, PageSpec


class QtWindowShell(QMainWindow):
    """Own the top-level Qt window and retained page-navigation lifecycle."""

    def __init__(
        self,
        *,
        title: str,
        on_close: Callable[[], None] | None = None,
        parent: QMainWindow | None = None,
    ) -> None:
        QMainWindow.__init__(self, parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 680)
        self.resize(1040, 760)
        self._on_close = on_close
        self._close_notified = False
        self.page_stack = QStackedWidget(self)
        self.page_stack.setObjectName("applicationPages")
        self.page_stack.setAccessibleName("Application pages")
        self.setCentralWidget(self.page_stack)
        self._page_router = PageRouter(self.page_stack)

    @property
    def active_page(self) -> str | None:
        return self._page_router.active_key

    def register_page(self, key: str, page: Any) -> None:
        """Retain one child QWidget under a stable navigation key."""

        if not hasattr(page, "show") or not hasattr(page, "hide"):
            raise TypeError("Qt page must be a QWidget")
        page.setParent(self.page_stack)
        self.page_stack.addWidget(page)
        self._page_router.register(PageSpec(key, lambda _host: page))

    def show_page(self, key: str) -> Any:
        page = self._page_router.show(key)
        self.page_stack.setCurrentWidget(page)
        return page

    def page(self, key: str) -> Any:
        return self._page_router.get(key)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._close_notified:
            self._close_notified = True
            if self._on_close is not None:
                self._on_close()
        event.accept()
        super().closeEvent(event)
