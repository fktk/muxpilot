# Auto-Expand New Windows in Tree View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a new tmux window (or session/pane) appears after a tree refresh, its node is automatically expanded while previously existing nodes keep their previous fold state.

**Architecture:** Track every node's path from the previous `populate()` call in `_known_paths`. During state restoration, expand nodes whose path is new (not in `_known_paths`) in addition to those the user previously expanded.

**Tech Stack:** Python, Textual (Tree widget), pytest

---

### Task 1: Write the failing test

**Files:**
- Test: `tests/test_tree_view.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tree_view.py`:

```python
def test_new_window_is_auto_expanded():
    """Newly added windows should be expanded automatically."""
    tree1 = make_tree(sessions=[
        make_session(session_id="$0", windows=[
            make_window(window_id="@0", panes=[
                make_pane(pane_id="%0"),
            ])
        ])
    ])
    tw = TmuxTreeView()
    tw.populate(tree1)

    # First population: everything expanded by default
    session_node = tw.root.children[0]
    window1_node = session_node.children[0]
    assert window1_node.is_expanded

    # Collapse the existing window manually to simulate user action
    window1_node.collapse()
    assert not window1_node.is_expanded

    # Second population: add a new window
    tree2 = make_tree(sessions=[
        make_session(session_id="$0", windows=[
            make_window(window_id="@0", panes=[
                make_pane(pane_id="%0"),
            ]),
            make_window(window_id="@1", panes=[
                make_pane(pane_id="%1"),
            ]),
        ])
    ])
    tw.populate(tree2)

    session_node = tw.root.children[0]
    window1_node = session_node.children[0]
    window2_node = session_node.children[1]

    # Previously existing window should stay collapsed
    assert not window1_node.is_expanded
    # New window should be auto-expanded
    assert window2_node.is_expanded
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_tree_view.py::test_new_window_is_auto_expanded -v
```

Expected: **FAIL** — `window2_node.is_expanded` is `False` because the new window gets collapsed by `_restore_state()`.

---

### Task 2: Implement the fix

**Files:**
- Modify: `src/muxpilot/widgets/tree_view.py`

- [ ] **Step 3: Write minimal implementation**

In `src/muxpilot/widgets/tree_view.py`:

1. In `__init__`, add:
```python
self._known_paths: set[str] = set()
```

2. In `_save_state()`, after saving expanded paths, also save all known paths:
```python
    def _save_state(self) -> None:
        """Save the expanded state of all nodes and the currently selected node."""
        self._expanded_paths.clear()
        self._known_paths.clear()
        
        # Save expanded nodes and all known nodes
        nodes_to_check: list[TreeNode[Text]] = [self.root]
        while nodes_to_check:
            node = nodes_to_check.pop(0)
            if node != self.root:
                path = self._get_node_path(node)
                if path:
                    self._known_paths.add(path)
                    if node.is_expanded:
                        self._expanded_paths.add(path)
            nodes_to_check.extend(node.children)

        # Save selected node
        if self.cursor_node and self.cursor_node != self.root:
            self._selected_path = self._get_node_path(self.cursor_node)
        else:
            self._selected_path = None
```

3. In `_restore_state()`, change the expansion logic:
```python
    def _restore_state(self) -> None:
        """Restore the expanded state and selection."""
        nodes_to_check: list[TreeNode[Text]] = [self.root]
        target_cursor_node = None
        
        while nodes_to_check:
            node = nodes_to_check.pop(0)
            if node != self.root:
                path = self._get_node_path(node)
                if path in self._expanded_paths or path not in self._known_paths:
                    node.expand()
                else:
                    node.collapse()
                if path == self._selected_path:
                    target_cursor_node = node
            nodes_to_check.extend(node.children)

        if target_cursor_node:
            # Defer until after rendering: newly added nodes have _line == -1
            # until the tree renders, so move_cursor() would snap to line -1
            # (top) if called synchronously here.
            self.call_after_refresh(self._move_cursor_and_emit, target_cursor_node)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_tree_view.py::test_new_window_is_auto_expanded -v
```

Expected: **PASS**

- [ ] **Step 5: Run full test suite**

Run:
```bash
uv run pytest tests/ -v
```

Expected: **All 201 tests pass** (200 existing + 1 new).

- [ ] **Step 6: Commit**

```bash
git add src/muxpilot/widgets/tree_view.py tests/test_tree_view.py
git commit -m "feat: auto-expand newly created windows in tree view"
```
