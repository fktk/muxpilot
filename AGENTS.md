# AGENTS.md

## プロジェクト概要

muxpilot — tmux session/window/pane をナビゲートする TUI ツール。AIエージェントオーケストレーション用途。

## 開発ルール

- **TDD**: テストを先に書き、実装してからテストを通す。
- **パッケージ管理**: `uv` を使う。`pip` や `poetry` は使わない。
- **Python 実行**: `uv run ...` で実行する。

## コマンド

```bash
uv sync              # 依存インストール
uv run muxpilot      # アプリ起動
uv run pytest tests/ -v  # テスト実行
```

## 構成

```
src/muxpilot/
├── app.py           # Textual App（レイアウト・キーバインド）
├── models.py        # データモデル（Session/Window/Pane/PaneStatus）
├── tmux_client.py   # libtmux ラッパー
├── watcher.py       # ポーリング監視・パターン検出
└── widgets/         # TUI ウィジェット（tree_view, detail_panel, status_bar）

tests/
├── conftest.py      # 共通フィクスチャ・モックファクトリ
├── test_models.py
├── test_tmux_client.py
├── test_watcher.py
└── test_app.py
```

## テスト方針

- libtmux は `unittest.mock` でモック化し、tmux サーバー不要でテスト可能にする。
- Textual ウィジェットは `App.run_test()` で非同期テスト。
- `conftest.py` のファクトリ関数（`make_pane`, `make_tree`, `make_mock_client` 等）を使う。
