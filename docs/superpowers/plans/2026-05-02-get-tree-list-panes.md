# get_tree() → tmux list-panes -a -F 移行計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** TmuxClient.get_tree() を libtmux の逐次プロパティアクセスから tmux list-panes -a -F による一括取得に置き換え、tmux コマンド発行回数を 1 poll あたり数十〜数百回から 1回 に減らす。

**Architecture:** subprocess.run でタブ区切り出力を取得し、各行をパースして TmuxTree を構築する。capture_pane_content() や navigate_to() は引き続き libtmux を利用。

**Tech Stack:** Python 3.12, subprocess, libtmux (partial), pytest, unittest.mock

---

## File Map

| File | Responsibility | Change |
|------|---------------|--------|
| src/muxpilot/tmux_client.py | TmuxClient — get_tree() のリファクタリング | get_tree() を subprocess.run ベースに書き換え |
| tests/test_tmux_client.py | TmuxClient のユニットテスト | TestGetTree を subprocess.run モックに書き換え |
| tests/conftest.py | 共通モックファクトリ | 変更なし |
| tests/test_app.py | App 統合テスト | 変更なし |

---

## Task 1: TmuxClient.get_tree() のリファクタリング

**Files:**
- Modify: src/muxpilot/tmux_client.py

- [ ] **Step 1: get_tree() の新実装を追加する**

get_tree() を subprocess.run(["tmux", "list-panes", "-a", "-F", fmt]) で書き換える。出力はタブ区切り15フィールド。

フォーマット:
- #{session_name} #{session_id} #{session_attached}
- #{window_id} #{window_name} #{window_index} #{window_active}
- #{pane_id} #{pane_index} #{pane_current_command} #{pane_current_path}
- #{pane_active} #{pane_width} #{pane_height} #{pane_pid}

各行をパースして sessions と windows の dict を構築し、最後に TmuxTree を返す。失敗時は空の TmuxTree を返す。

- [ ] **Step 2: 文字列パース用ヘルパーを追加する**

_is_attached_str(value: str) -> bool と _is_active_str(value: str) -> bool を追加。int() 変換を試み、失敗時は False を返す。

- [ ] **Step 3: 既存の libtmux ベースヘルパーを整理する**

_is_attached, _is_active_window, _is_active_pane は _find_pane() 内部で libtmux オブジェクトに使うためそのまま維持。get_tree() では新しい _is_attached_str / _is_active_str を使う。

---

## Task 2: tests/test_tmux_client.py の TestGetTree を書き換える

**Files:**
- Modify: tests/test_tmux_client.py

- [ ] **Step 1: subprocess.run 用モックヘルパーを追加する**

_list_panes_output(lines: list[str]) -> object を追加。stdout, stderr, returncode を持つ簡易オブジェクトを返す。

- [ ] **Step 2: test_basic を書き換える**

subprocess.run を patch して1行の出力を返し、get_tree() が正しくパースされることを確認。

- [ ] **Step 3: test_multiple を書き換える**

4行の出力（2 sessions, 3 windows, 4 panes）をモックし、構造が正しく構築されることを確認。

- [ ] **Step 4: test_empty を書き換える**

空の stdout をモックし、total_sessions == 0 であることを確認。

- [ ] **Step 5: test_none_values を書き換える**

タブ区切りの空フィールドを含む行をモックし、デフォルト値（空文字、0）で正しく初期化されることを確認。

- [ ] **Step 6: 不要な libtmux モックヘルパーを削除する**

_mock_pane, _mock_window, _mock_session, _client_with は TestGetTree でしか使われていないため削除。TestCapture / TestNavigateTo / TestGetFullCommand は個別にモックを作っているため影響なし。

---

## Task 3: _find_pane() の libtmux fallback を維持する

**Files:**
- Modify: src/muxpilot/tmux_client.py

- [ ] **Step 1: _find_pane() の実装を維持する**

capture_pane_content() は libtmux.Pane オブジェクトの capture_pane() メソッドを必要とするため、_find_pane() は libtmux fallback を維持する。_pane_cache は get_tree() では更新しない（list-panes では libtmux.Pane を取得できないため）。

---

## Task 4: テスト実行とコミット

- [ ] **Step 1: 全テストを実行する**

Run: uv run pytest tests/ -v
Expected: 全テストパス

- [ ] **Step 2: コミットする**

git add src/muxpilot/tmux_client.py tests/test_tmux_client.py
git commit -m "refactor: replace get_tree() with list-panes -a -F for fewer tmux commands"

---

## Self-Review

### 1. Spec coverage
- get_tree() を list-panes -a -F に置き換える → Task 1 で対応
- tmux コマンド発行回数を 1回 に減らす → list-panes -a -F は1回のコマンド
- 既存機能維持 → capture_pane_content(), navigate_to(), kill_pane() は変更なし
- テスト更新 → Task 2 で対応

### 2. Placeholder scan
- すべてのステップに具体的な内容を記載済み
- TBD, TODO なし

### 3. Type consistency
- PaneInfo, WindowInfo, SessionInfo, TmuxTree の型は models.py と一致
- 新ヘルパーは str -> bool のシグネチャ

---

## Execution Handoff

Plan complete and saved to docs/superpowers/plans/2026-05-02-get-tree-list-panes.md.

Two execution options:

1. Subagent-Driven (recommended) - Dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
