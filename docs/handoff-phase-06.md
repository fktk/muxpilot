# muxpilot リファクタリング — フェーズ 6 完了時点のハンドオフドキュメント

> **作成日**: 2026-05-03  
> **最終コミット**: `ac9d619` — refactor: split monolithic test_app.py into 9 focused test modules (#36)  
> **テスト結果**: 236 passed / 0 failed  
> **現在のブランチ**: `master` (ローカルで 6 コミット先行)

---

## 1. これまで完了したフェーズ

| フェーズ | PR # | 内容 | テスト数 |
|---------|------|------|---------|
| Phase 1 | #30 | `TmuxClient` から `TreeParser` を抽出、デッドコード削除 | 218 |
| Phase 2 | #32 | `TmuxWatcher` を `PatternMatcher`, `StructuralChangeDetector`, `StatusTracker` に分解 | 225 |
| Phase 3 | #33 | `PollingController` → `TimerCoordinator`（コールバック方式）、`FilterState` を immutable に、`RenameController` → `PaneTitleManager` | 236 |
| Phase 4 | #34 | `app.py` から backward-compatible property delegates を削除 | 236 |
| Phase 5 | #35 | `tree_view.py` の O(n²) アニメーションループを O(n) に修正、`rich_to_markdown` を抽出 | 236 |
| Phase 6 | #36 | `test_app.py`（1,380行）を 9 つの焦点モジュールに分解 | 236 |

---

## 2. 残っているタスク（優先順位順）

### Phase 7: `app.py` のさらなる分解（優先度: 中〜高）

**現状**: `src/muxpilot/app.py` は依然として **481行** で、以下が混在している：
- Compose レイアウト（`compose()`, `watch_theme()`）
- キーイベントハンドラ（`action_*` メソッド群 10個以上）
- ポーリングコールバックと UI 更新（`_handle_poll_result`, `_update_ui_from_poll`）
- フィルター/リネーム状態遷移（`on_input_changed`, `on_input_submitted`, `_finish_rename`）
- 通知チェックループ（`_check_notifications`）
- モーダルハンドラ（`_on_kill_modal_dismissed`）

**抽出候補**（必ずしも全て実施する必要はない。最も価値の高いものから）：

1. **`AppComposer`** — `compose()` / `watch_theme()` / CSS 定義などレイアウト責任
2. **`ActionHandler`** — `action_*` メソッド群（キーイベント処理）
3. **`UIOrchestrator`** — `_do_refresh`, `_update_ui_from_poll`, `_check_notifications`

**注意**: `app.py` は Textual の `App` クラスを継承している。Textual の event routing（`on_*` メソッド）が `App` インスタンスに依存するため、単純な移動では event handler が機能しなくなる。以下のいずれかの手法を検討：
- **手法A**: `App` 継承を維持し、内部で helper クラスに委譲（推奨）
- **手法B**: `App` 継承を維持し、mix-in クラスに分割
- **手法C**: あまり分解せず、Phase 7 をスキップして Phase 8〜10 に進む

**テストへの影響**: `test_app_*.py` は `App.run_test()` で動作しており、分解後も各テストファイルは変更なしで動作すべき。

### Phase 8: `controllers.py` の alias 削除（優先度: 中）

**現状**: `src/muxpilot/controllers.py` に以下の backward-compatible alias が残存：

```python
# Backward-compatible alias
PollingController = TimerCoordinator

# Backward-compatible alias
RenameController = PaneTitleManager
```

**手順**:
1. `app.py` を確認し、`PollingController` / `RenameController` の参照がないことを確認（Phase 4 で既に除去済みのはず）
2. `controllers.py` から alias 行を削除
3. `tests/` 全体を grep して alias 参照がないことを確認
4. テスト実行 → 全 green ならコミット

### Phase 9: 型安全性の改善（優先度: 低〜中）

**対象箇所**:
- `timer_coordinator.py` の `set_interval` 引数: `Callable[..., Any]` → より具体的な型に
- `_notify_channel`, `_label_store` property setter の `value` 引数に型注釈がない
- `watcher.py` の `prompt_patterns` / `error_patterns` property delegates に型注釈がない

**注意**: 過度に複雑な型（Textual の内部型など）を import しない。`typing` モジュールの標準的な型で十分。

### Phase 10: デッドコード・未使用 import の削除（優先度: 低）

**現状**:
- `app.py` の `MAX_POLL_BACKOFF_SECONDS` — 使われず（`timer_coordinator.py` に移動済み）
- `controllers.py` の未使用 import: `MAX_POLL_BACKOFF_SECONDS`, `DEFAULT_MAX_CONSECUTIVE_FAILURES`, `DEFAULT_COOLDOWN_SECONDS`, `TmuxClient`
- `tests/` の未使用 import を確認

**手順**:
1. `ruff check src/ tests/` または `flake8` で未使用 import を検出（インストールされていなければ `uv add --dev ruff`）
2. 未使用変数・import を削除
3. テスト実行 → 全 green ならコミット

### Phase 11: `AGENTS.md` / 構成図の更新（優先度: 低）

**現状**: `AGENTS.md` のファイル構成図が古い：
- `timer_coordinator.py`, `pattern_matcher.py`, `structural_detector.py`, `status_tracker.py`, `tree_parser.py` が未記載
- `controllers.py` の役割記述が Phase 3 以前のまま

**手順**:
1. `src/muxpilot/` と `tests/` の実際のファイル一覧を確認
2. `AGENTS.md` の「構成」セクションを更新
3. 各ファイルの責任記述を現在の実装に合わせて更新

---

## 3. 現在のファイル構成

```
src/muxpilot/
├── __init__.py
├── app.py                  # 481行 — Textual App（レイアウト・キーバインド）
├── controllers.py          # 55行 — FilterState, PaneTitleManager（alias あり）
├── models.py               # 194行 — Session/Window/Pane/PaneStatus データモデル
├── pattern_matcher.py      # 55行 — 出力パターン検出（waiting/error/active）
├── status_tracker.py       # 65行 — ペインごとの履歴・idle 秒数追跡
├── structural_detector.py  # 74行 — セッション/ウィンドウ/ペインの増減検出
├── timer_coordinator.py    # 93行 — ポーリングタイマー・バックオフ・クールダウン
├── tmux_client.py          # 179行 — libtmux ラッパー
├── tree_parser.py          # 98行 — tmux list-panes 出力パース
├── watcher.py              # 165行 — ポーリング監視・イベント生成（統合層）
├── label_store.py          # 106行 — TOML 永続化
├── notify_channel.py       # 78行 — FIFO ベース外部通知受信
├── widgets/
│   ├── __init__.py
│   ├── detail_panel.py     # 129行 — 選択ノード詳細表示
│   ├── filter_bar.py       # 42行 — フィルター状態バー
│   ├── status_bar.py       # 44行 — ステータスバー
│   └── tree_view.py        # 278行 — ツリーウィジェット
├── screens/
│   ├── __init__.py
│   ├── help_screen.py      # 28行 — ヘルプ画面
│   └── kill_modal.py       # 42行 — Kill pane 確認モーダル

tests/
├── conftest.py             # 共通フィクスチャ・モックファクトリ
├── _test_app_common.py     # _patched_app() ヘルパー（Phase 6 で新設）
├── test_app_detail_panel.py
├── test_app_filter.py
├── test_app_kill.py
├── test_app_main.py
├── test_app_navigation.py
├── test_app_notifications.py
├── test_app_polling.py
├── test_app_rename.py
├── test_app_ui.py
├── test_filter_bar.py
├── test_help_screen.py
├── test_kill_modal.py
├── test_label_store.py
├── test_models.py
├── test_pattern_matcher.py
├── test_rename_controller.py
├── test_status_tracker.py
├── test_structural_detector.py
├── test_timer_coordinator.py
├── test_tmux_client.py
├── test_tree_parser.py
├── test_tree_view.py
├── test_watcher.py
└── test_watcher_config.py
```

---

## 4. 開発ルール（変更禁止）

以下は全フェーズを通じて厳守されたルール。変更しないこと。

1. **TDD**: テストを先に書き、実装してからテストを通す。
2. **パッケージ管理**: `uv` のみ。`pip`/`poetry` は使わない。
3. **Python 実行**: `uv run ...` で実行。
4. **機能開発ブランチ（必須）**: すべての機能開発・バグ修正は、**必ず git worktree を使って独立したディレクトリで行う**。main ブランチへの直接コミット、および同じワークディレクトリでのブランチ切り替えは禁止。
   - ディレクトリ: `.worktrees/` を優先（なければ作成）
   - セットアップ: `git worktree add .worktrees/<branch> -b <branch>` → `cd .worktrees/<branch>` → `uv sync`
   - ベースラインテスト: `uv run pytest tests/ -v` を必ず実行
   - 作業完了後: `finishing-a-development-branch` スキルに従いマージ/PR/破棄の選択
5. **コミットメッセージ**: 簡潔に変更の「なぜ」を書く。`refactor:`, `perf:`, `test:` 等のプレフィックスを使用。

---

## 5. 既知の技術的負債

| 優先度 | 内容 | 場所 |
|--------|------|------|
| 中〜高 | `app.py` の責任分離 | `src/muxpilot/app.py` (481行) |
| 中 | `controllers.py` の alias 削除 | `src/muxpilot/controllers.py` |
| 低〜中 | 型安全性の改善 | `timer_coordinator.py`, `watcher.py` |
| 低 | デッドコード・未使用 import | `app.py`, `controllers.py` |
| 低 | `AGENTS.md` の構成図更新 | `AGENTS.md` |

---

## 6. 未完了の別ブランチ

ワークツリー `.worktrees/fix-capture-pane-empty-lines` にブランチ `fix-capture-pane-empty-lines` が残存（コミット `2dfce9c`）。
これは今回のリファクタリングとは無関係な既存ブランチ。マージ済みか確認が必要な場合は別途調査。

---

## 7. 推奨する次のアクション

1. **Phase 8（alias 削除）** を実施 — 最も安全で工数が少ない
2. **Phase 10（デッドコード削除）** を実施 — `ruff` で機械的に検出可能
3. **Phase 9（型安全性）** を実施 — 影響範囲が小さい
4. **Phase 7（app.py 分解）** を判断 — 価値が高いが工数も大きい。Textual の event routing との兼ね合いを慎重に検討
5. **Phase 11（ドキュメント更新）** を最後に実施

---

## 8. コマンドリファレンス

```bash
# 依存インストール（dev も含む）
uv sync

# テスト実行（全テスト）
uv run pytest tests/ -v

# テスト実行（単一ファイル）
uv run pytest tests/test_app_polling.py -v

# アプリ起動
uv run muxpilot

# 未使用 import 検出（ruff をインストールする場合）
uv add --dev ruff
uv run ruff check src/ tests/
```

---

*このドキュメントは Phase 6 完了時点で作成された。以降のフェーズが実施された場合、このファイルを更新または削除すること。*
