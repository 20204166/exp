# UI Spacing Token Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline padding/wrap literals in `maintenance/ui/layout.py` and `settings_home.py` with canonical `styles.SPACING`/`styles.LAYOUT` tokens so spacing has exactly one source of truth.

**Architecture:** `styles.py` already owns the design tokens (`SPACING`, `LAYOUT`, `CONTROL`). `layout.py` is the single widget-construction owner but bypasses the token map with ~11 inline padding literals and 3 hard-coded wrap widths. We add the missing semantic tokens, migrate every literal to a token (reusing existing `section_gap`/`row_gap`/`control_gap` where the value already exists), pin the historical values with a parity test, and remove the now-redundant `settings_home._CARD_WRAP` constant. No new coordinator is introduced — spacing is static data, and a runtime coordinator for it would duplicate the existing token registry (see analysis).

**Tech Stack:** Python 3.10+, tkinter, `unittest`. Tokens are plain `dict[str, int]` values consumed at import time.

---

## File Structure Map

- `maintenance/ui/styles.py` — extend `SPACING` (+7 tokens) and `LAYOUT` (+6 tokens). This is the canonical token owner; no behavior changes.
- `maintenance/ui/layout.py` — migrate inline literals to tokens; `SCROLLBAR_GUTTER` becomes a token-derived alias. Single construction owner stays.
- `maintenance/ui/settings_home.py` — delete `_CARD_WRAP`; use `LAYOUT["navigation_card_wrap"]`.
- `tests/test_ui_primitives.py` — add `SpacingTokenParityTests` that pins every historical literal value so the migration cannot silently change the UI.
- Regression net: existing `tests/test_ui_primitives.py`, `tests/test_live_tk_resize.py`, `tests/test_dashboard_ui.py`, `tests/dump_ui.py` assert pack geometry/wrap widths and will catch any drift.

## Task Overview

- **Task 1:** Add tokens + parity test (TDD: test fails first, tokens make it pass).
- **Task 2:** Migrate `layout.py` scrollbar/footer/dialog paddings.
- **Task 3:** Migrate `layout.py` header/page-shell/section/navigation paddings and wrap widths.
- **Task 4:** Migrate `layout.py` event/setting rows + `settings_home._CARD_WRAP`.
- **Task 5:** Full validation and commit.

---

### Task 1: Add spacing/layout tokens and the parity test

**Files:**
- Modify: `maintenance/ui/styles.py:59-89`
- Test: `tests/test_ui_primitives.py`

- [ ] **Step 1: Write the failing parity test**

Add to `tests/test_ui_primitives.py`, after `DesignTokenParityTests`:

```python
class SpacingTokenParityTests(unittest.TestCase):
    def test_spacing_tokens_match_historical_layout_literals(self) -> None:
        self.assertEqual(ui_styles.SPACING["scrollbar_gutter"], 6)
        self.assertEqual(ui_styles.SPACING["caption_gap"], 2)
        self.assertEqual(ui_styles.SPACING["header_desc_gap"], 6)
        self.assertEqual(ui_styles.SPACING["header_actions_gap"], 20)
        self.assertEqual(ui_styles.SPACING["heading_desc_gap"], 4)
        self.assertEqual(ui_styles.SPACING["section_body_top"], 10)
        self.assertEqual(ui_styles.SPACING["nav_button_gap"], 16)
        self.assertEqual(ui_styles.LAYOUT["dashboard_header_wrap"], 680)
        self.assertEqual(ui_styles.LAYOUT["page_shell_wrap"], 620)
        self.assertEqual(ui_styles.LAYOUT["navigation_card_wrap"], 560)
        self.assertEqual(ui_styles.LAYOUT["section_description_wrap"], 360)
        self.assertEqual(ui_styles.LAYOUT["fit_wrap_margin"], 36)
        self.assertEqual(ui_styles.LAYOUT["fit_wrap_max"], 560)

    def test_scrollbar_gutter_derives_from_spacing_token(self) -> None:
        self.assertEqual(ui_layout.SCROLLBAR_GUTTER, ui_styles.SPACING["scrollbar_gutter"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_ui_primitives.SpacingTokenParityTests -v`
Expected: `FAIL`/`ERROR` — `KeyError: 'scrollbar_gutter'` (tokens do not exist yet).

- [ ] **Step 3: Add the new tokens**

In `maintenance/ui/styles.py`, extend the `SPACING` dict (currently lines 59-73):

```python
SPACING: dict[str, int] = {
    "page_x": 30,
    "page_y": 26,
    "section_gap": 14,
    "row_gap": 10,
    "control_gap": 12,
    "card_pad_x": 18,
    "card_pad_y": 16,
    "section_pad_x": 18,
    "section_pad_y": 14,
    "dialog_pad_x": 24,
    "dialog_pad_y": 22,
    "button_gap": 8,
    "footer_gap": 16,
    "scrollbar_gutter": 6,
    "caption_gap": 2,
    "header_desc_gap": 6,
    "header_actions_gap": 20,
    "heading_desc_gap": 4,
    "section_body_top": 10,
    "nav_button_gap": 16,
}
```

Extend the `LAYOUT` dict (currently lines 84-89):

```python
LAYOUT: dict[str, int] = {
    "dashboard_description_wrap": 520,
    "dashboard_status_wrap": 280,
    "card_grid_gap": 7,
    "card_row_gap": 14,
    "dashboard_header_wrap": 680,
    "page_shell_wrap": 620,
    "navigation_card_wrap": 560,
    "section_description_wrap": 360,
    "fit_wrap_margin": 36,
    "fit_wrap_max": 560,
}
```

- [ ] **Step 4: Run the parity test to verify it passes**

Run: `python3 -m unittest tests.test_ui_primitives.SpacingTokenParityTests -v`
Expected: `ok` for both tests.

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/styles.py tests/test_ui_primitives.py
git commit -m "style: add spacing and layout tokens for layout module"
```

---

### Task 2: Migrate scrollbar, footer and dialog paddings in layout.py

**Files:**
- Modify: `maintenance/ui/layout.py:22-23, 344-371`

- [ ] **Step 1: Make `SCROLLBAR_GUTTER` derive from its token**

In `maintenance/ui/layout.py` (lines 22-23):

```python
SCROLLBAR_GUTTER = ui_styles.SPACING["scrollbar_gutter"]
FOOTER_GUTTER = ui_styles.SPACING["footer_gap"]
```

- [ ] **Step 2: Migrate `dialog_footer` default padding**

In `dialog_footer` (line 351), change the default:

```python
def dialog_footer(
    container: Any,
    *,
    frame_cls: Callable[..., Any],
    label_cls: Callable[..., Any],
    colors: dict[str, str],
    status_text: str,
    pady: tuple[int, int] = (ui_styles.SPACING["section_gap"], 0),
) -> tuple[Any, Any]:
```

- [ ] **Step 3: Run the affected layout tests**

Run: `python3 -m unittest tests.test_ui_primitives -v`
Expected: all `ok` (values unchanged; `SCROLLBAR_GUTTER` and the footer default equal the old literals).

- [ ] **Step 4: Commit**

```bash
git add maintenance/ui/layout.py
git commit -m "style: token-drive scrollbar and dialog footer spacing"
```

---

### Task 3: Migrate header, page-shell and section-card spacing

**Files:**
- Modify: `maintenance/ui/layout.py:374-539`

- [ ] **Step 1: Migrate `dashboard_header`**

In `dashboard_header` (lines 374-429):
- Change the signature default `wrap: int = 680` → `wrap: int = ui_styles.LAYOUT["dashboard_header_wrap"]`.
- Node label `.pack(anchor="w", pady=(2, 0))` (line 410) → `pady=(ui_styles.SPACING["caption_gap"], 0)`.
- Description `.pack(anchor="w", pady=(6, 0))` (line 416) → `pady=(ui_styles.SPACING["header_desc_gap"], 0)`.
- Actions `actions.pack(side="right", padx=(20, 0))` (line 424) → `padx=(ui_styles.SPACING["header_actions_gap"], 0)`.

- [ ] **Step 2: Migrate `page_shell`**

In `page_shell` (lines 432-487):
- `wrap=620` (line 462) → `wrap=ui_styles.LAYOUT["page_shell_wrap"]`.
- `body.pack(fill="both", expand=True, pady=(14, 0))` (line 473) → `pady=(ui_styles.SPACING["section_gap"], 0)`.

- [ ] **Step 3: Migrate `section_card`**

In `section_card` (lines 490-539):
- `card.pack(fill="x", pady=(0, 14))` (line 517) → `pady=(0, ui_styles.SPACING["section_gap"])`.
- Description `wraplength=360` (line 532) → `wraplength=ui_styles.LAYOUT["section_description_wrap"]`.
- Description `.pack(anchor="w", pady=(4, 0))` (line 535) → `pady=(ui_styles.SPACING["heading_desc_gap"], 0)`.
- `resize_aware(card, fit_wrap_to_width(description_label, 560, margin=36))` (line 536) → `resize_aware(card, fit_wrap_to_width(description_label, ui_styles.LAYOUT["fit_wrap_max"], margin=ui_styles.LAYOUT["fit_wrap_margin"]))`.
- `body.pack(fill="x", pady=(10, 0))` (line 538) → `pady=(ui_styles.SPACING["section_body_top"], 0)`.

- [ ] **Step 4: Run the affected tests**

Run: `python3 -m unittest tests.test_ui_primitives tests.test_settings_home tests.test_preferences_page -v`
Expected: all `ok`.

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/layout.py
git commit -m "style: token-drive header, page-shell and section spacing"
```

---

### Task 4: Migrate navigation-card, event-row and setting-row spacing

**Files:**
- Modify: `maintenance/ui/layout.py:542-712`
- Modify: `maintenance/ui/settings_home.py:23,142`

- [ ] **Step 1: Migrate `navigation_card`**

In `navigation_card` (lines 542-599):
- `wraplength: int = 560` (line 555) → `wraplength: int = ui_styles.LAYOUT["navigation_card_wrap"]`.
- `card.pack(fill="x", pady=(0, 14))` (line 569) → `pady=(0, ui_styles.SPACING["section_gap"])`.
- Description `.pack(anchor="w", pady=(4, 0))` (line 587) → `pady=(ui_styles.SPACING["heading_desc_gap"], 0)`.
- `button.pack(side="right", padx=(16, 0), anchor="center")` (line 595) → `padx=(ui_styles.SPACING["nav_button_gap"], 0)`.

- [ ] **Step 2: Migrate `event_row`**

In `event_row` (line 661):
- `button.pack(side="right", padx=(12, 0))` → `padx=(ui_styles.SPACING["control_gap"], 0)`.

- [ ] **Step 3: Migrate `setting_row`**

In `setting_row` (lines 665-712):
- `row.pack(fill="x", pady=(0, 10))` (line 686) → `pady=(0, ui_styles.SPACING["row_gap"])`.
- `control.pack(side="right", padx=(12, 0))` (line 699) → `padx=(ui_styles.SPACING["control_gap"], 0)`.
- `help_label.pack(anchor="w", pady=(2, 0))` (line 711) → `pady=(ui_styles.SPACING["caption_gap"], 0)`.

- [ ] **Step 4: Migrate `settings_home._CARD_WRAP`**

In `maintenance/ui/settings_home.py`:
- Delete line 23 (`_CARD_WRAP = 560`).
- Line 142 `wraplength=_CARD_WRAP` → `wraplength=ui_styles.LAYOUT["navigation_card_wrap"]`.
- `ui_styles` is already imported at line 20 (`from maintenance.ui import styles as ui_styles`), so no import change is needed.

- [ ] **Step 5: Run the affected tests**

Run: `python3 -m unittest tests.test_ui_primitives tests.test_settings_home tests.test_preferences_page tests.test_nodes_connections_page tests.test_cluster_page -v`
Expected: all `ok`.

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/layout.py maintenance/ui/settings_home.py
git commit -m "style: token-drive navigation, event and setting row spacing"
```

---

### Task 5: Final validation and commit

**Files:** none (validation only)

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s tests -q`
Expected: `Ran 1251 tests ... OK` (no regressions; count may shift only if the live-Tk test skips).

- [ ] **Step 2: Run static sanity checks**

Run: `python3 -m compileall -q maintenance tests && git diff --check`
Expected: exit 0, no output.

- [ ] **Step 3: Verify no fully-literal padding tuples remain in the touched surface**

Run: `grep -nE "pady=\([0-9]+, [0-9]+\)|padx=\([0-9]+, [0-9]+\)" maintenance/ui/layout.py`
Expected: no output (only token references and non-numeric tuples like `(0, FOOTER_GUTTER)` remain).

- [ ] **Step 4: Commit any leftover changes**

```bash
git add -A
git commit -m "style: finalize spacing token consolidation"
```
Only run if Step 3 found stragglers; otherwise skip.

---

## Self-Review Notes

- **Spec coverage:** Every inline padding/wrap literal in `layout.py` listed in the analysis maps to a token in Task 1 and a migration in Tasks 2-4. `settings_home._CARD_WRAP` is covered in Task 4. Existing token users (`dashboard_page.py`, `window_pages.py`, `window_components.py`) are left untouched because they already use tokens.
- **No placeholders:** All steps carry exact code, paths, commands and expected output.
- **Type consistency:** Token names are defined once in Task 1 and reused verbatim in Tasks 2-4 (`scrollbar_gutter`, `caption_gap`, `header_desc_gap`, `header_actions_gap`, `heading_desc_gap`, `section_body_top`, `nav_button_gap`, `dashboard_header_wrap`, `page_shell_wrap`, `navigation_card_wrap`, `section_description_wrap`, `fit_wrap_margin`, `fit_wrap_max`, plus existing `section_gap`, `row_gap`, `control_gap`).
- **Bounded scope:** `dialogs.py`'s ~90 inline paddings are deliberately NOT migrated here (separate, larger surface); the plan fixes the canonical owner (`layout.py`) first. No new coordinator is created.