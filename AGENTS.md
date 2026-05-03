# AGENTS.md

## プロジェクト概要

muxpilot — tmux session/window/pane をナビゲートする TUI ツール。AIエージェントオーケストレーション用途。

## 開発ルール

- **TDD**: テストを先に書き、実装してからテストを通す。
- **パッケージ管理**: `uv` を使う。`pip` や `poetry` は使わない。
- **Python 実行**: `uv run ...` で実行する。
- **機能開発ブランチ（必須）**: すべての機能開発・バグ修正は、**必ず git worktree を使って独立したディレクトリで行う**。main ブランチへの直接コミット、および同じワークディレクトリでのブランチ切り替えは禁止。
  
  1. **ディレクトリ選定**: `.worktrees/` を優先（なければ作成）。`worktrees/` は代替。両方存在する場合は `.worktrees/` を使用する。
  2. **.gitignore 確認**: プロジェクトローカルの worktree ディレクトリを作成・使用前に、必ず `.gitignore` に含まれているか確認する (`git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null`)。含まれていない場合は、**即座に `.gitignore` に追加しコミットしてから** worktree を作成する。
  3. **セットアップ**: `git worktree add .worktrees/<branch> -b <branch>` → `cd .worktrees/<branch>` → `uv sync`
  4. **ベースラインテスト**: 作業開始前に必ず `uv run pytest tests/ -v` を実行し、クリーンな状態であることを確認する。テストが失敗する場合は失敗内容を報告し、明示的な確認を取ってから作業を進める。
  5. **作業完了後**: `finishing-a-development-branch` スキルに従い、マージ/PR/保持/破棄の4つの選択肢を提示し、選択に応じてブランチ・worktree を適切にクリーンアップする。

## コマンド

```bash
uv sync                   # 依存インストール（dev 依存も含む）
uv run muxpilot           # アプリ起動（entrypoint: app.py の main()）
uv run pytest tests/ -v   # テスト実行
uv run pytest tests/test_watcher.py -v  # 単一ファイル
```

## 構成

```
src/muxpilot/
├── app.py              # Textual App（レイアウト・キーバインド・event handler の薄いラッパー）
├── app_actions.py      # キーイベントアクションの実装（ActionHandler）
├── app_ui.py           # ポーリング結果の UI 反映・詳細パネル更新（UIOrchestrator）
├── controllers.py      # FilterState, PaneTitleManager（ Pane リネーム・フィルター状態）
├── models.py           # データモデル（Session/Window/Pane/PaneStatus）
├── pattern_matcher.py  # 出力パターン検出（waiting/error/active）
├── status_tracker.py   # ペインごとの履歴・idle 秒数追跡
├── structural_detector.py  # セッション/ウィンドウ/ペインの増減検出
├── timer_coordinator.py    # ポーリングタイマー・バックオフ・クールダウン
├── tmux_client.py      # libtmux ラッパー
├── tree_parser.py      # tmux list-panes 出力パース
├── watcher.py          # ポーリング監視・イベント生成（統合層）
├── label_store.py      # テーマ・UI 設定の TOML 永続化
├── notify_channel.py   # FIFO ベースの外部通知受信
├── widgets/            # TUI ウィジェット（tree_view, detail_panel, filter_bar, status_bar）
└── screens/            # 画面・モーダル（help_screen, kill_modal）

tests/
├── conftest.py              # 共通フィクスチャ・モックファクトリ
├── _test_app_common.py      # _patched_app() ヘルパー
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
├── test_pane_title_manager.py
├── test_pattern_matcher.py
├── test_status_tracker.py
├── test_structural_detector.py
├── test_timer_coordinator.py
├── test_tmux_client.py
├── test_tree_parser.py
├── test_tree_view.py
├── test_watcher.py
└── test_watcher_config.py
```

## テスト方針

- libtmux は `unittest.mock` でモック化し、tmux サーバー不要でテスト可能にする。
- Textual ウィジェットは `App.run_test()` で非同期テスト（`@pytest.mark.asyncio`）。
- `conftest.py` のファクトリ関数（`make_pane`, `make_tree`, `make_mock_client`, `make_mock_notify_channel` 等）を使う。

## 設定ファイル

`~/.config/muxpilot/config.toml` に watcher のパターンや通知設定を設定できる。
`config.example.toml` を参照。設定値はデフォルトを完全に置き換える（マージではない）。
