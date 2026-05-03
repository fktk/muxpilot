# Auto-Expand New Windows in Tree View — Design Spec

> **Date:** 2026-05-03  
> **Status:** Approved

## Problem

When a new tmux window is created while muxpilot is running, the tree view repopulates but the new window node remains collapsed. The user must manually expand it to see its panes.

## Root Cause

`TmuxTreeView.populate()` preserves expansion state across refreshes by saving `_expanded_paths` before clearing the tree and restoring it afterward. A newly created window has a path that was never seen before, so it is not in `_expanded_paths` and gets collapsed by `_restore_state()`.

## Solution

Track which node paths existed in the **previous** tree population. During restoration, expand any node whose path is either:

1. In `_expanded_paths` (user explicitly expanded it before), **or**
2. **Not** in `_known_paths` (it is brand-new).

This preserves existing fold states while auto-expanding newly created sessions, windows, and panes.

## Changes

- **`src/muxpilot/widgets/tree_view.py`**
  - Add `_known_paths: set[str]` attribute.
  - In `_save_state()`, populate `_known_paths` with every non-root node's path (regardless of expansion state).
  - In `_restore_state()`, expand nodes whose path is **not** in `_known_paths`.

- **`tests/test_tree_view.py`**
  - Add a test that calls `populate()` twice with a second window added on the second call, asserting that the new window node is expanded.

## Non-Goals

- No changes to `app.py` or other widgets.
- No changes to the external API of `TmuxTreeView`.
- Does not affect manually collapsed nodes that existed before the refresh.

## Testing Strategy

Unit test in `tests/test_tree_view.py` using the existing mock-factory helpers (`make_tree`, `make_pane`).
