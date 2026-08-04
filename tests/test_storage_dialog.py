from collections.abc import Callable
import unittest
from datetime import datetime
from typing import Any
from pathlib import Path
from unittest.mock import patch

from maintenance.dialogs import StorageDialog
from maintenance.models import FileCandidate


class FakeTree:
    def __init__(self, selected: tuple[str, ...] = ()) -> None:
        self.selected = selected
        self.width = 755
        self.widths: dict[str, int] = {}

    def selection(self) -> tuple[str, ...]:
        return self.selected

    def winfo_width(self) -> int:
        return self.width

    def column(self, name: str, **options: int) -> None:
        self.widths[name] = options["width"]


class FakeControl:
    def config(self, **options: object) -> None:
        del options


class FakeManager:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def move_to_trash(self, paths: list[Path]) -> None:
        self.paths = paths


class StorageDialogTests(unittest.TestCase):
    def test_resize_columns_gives_remaining_width_to_file_path(self) -> None:
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree()

        dialog._resize_columns()
        self.assertEqual(
            dialog.tree.widths,
            {"path": 410, "reason": 140, "size": 85, "modified": 120},
        )

        dialog.tree.width = 915
        dialog._resize_columns()
        self.assertEqual(dialog.tree.widths["path"], 570)

    def test_move_selected_passes_all_selected_files_to_manager(self) -> None:
        first = Path("first.zip")
        second = Path("second.zip")
        candidates = {
            "0": FileCandidate(first, 10, datetime.now(), "Large file"),
            "1": FileCandidate(second, 20, datetime.now(), "Duplicate file"),
        }
        manager = FakeManager()
        dialog: Any = object.__new__(StorageDialog)
        dialog.tree = FakeTree(("0", "1"))
        dialog.candidates = candidates
        dialog.manager = manager
        dialog.scan_button = FakeControl()
        dialog.trash_button = FakeControl()
        dialog.status_label = FakeControl()

        def run_task(
            _widget: object,
            task: Callable[[], object],
            *_callbacks: object,
        ) -> None:
            task()

        with (
            patch("maintenance.dialogs.messagebox.askyesno", return_value=True),
            patch("maintenance.dialogs.run_in_thread", side_effect=run_task),
        ):
            dialog.move_selected()

        self.assertEqual(manager.paths, [first, second])


if __name__ == "__main__":
    unittest.main()
