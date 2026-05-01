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
├── app.py           # Textual App（レイアウト・キーバインド）
├── models.py        # データモデル（Session/Window/Pane/PaneStatus）
├── tmux_client.py   # libtmux ラッパー
├── watcher.py       # ポーリング監視・パターン検出（~/.config/muxpilot/config.toml で設定可）
├── label_store.py   # カスタムラベル・テーマの TOML 永続化
├── notify_channel.py # FIFO ベースの外部通知受信
└── widgets/         # TUI ウィジェット（tree_view, detail_panel, status_bar）

tests/
├── conftest.py      # 共通フィクスチャ・モックファクトリ
├── test_models.py
├── test_tmux_client.py
├── test_watcher.py
├── test_watcher_config.py
├── test_app.py
├── test_label_store.py
└── test_notify_channel.py
```

## テスト方針

- libtmux は `unittest.mock` でモック化し、tmux サーバー不要でテスト可能にする。
- Textual ウィジェットは `App.run_test()` で非同期テスト（`@pytest.mark.asyncio`）。
- `conftest.py` のファクトリ関数（`make_pane`, `make_tree`, `make_mock_client`, `make_mock_notify_channel` 等）を使う。

## 設定ファイル

`~/.config/muxpilot/config.toml` に watcher のパターンや通知設定を設定できる。
`config.example.toml` を参照。設定値はデフォルトを完全に置き換える（マージではない）。
