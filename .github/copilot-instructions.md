# muxpilot — Copilot 指示書

## コマンド

```bash
uv sync                              # 依存パッケージをインストール
uv run muxpilot                      # アプリを起動
uv run pytest tests/ -v              # 全テストを実行
uv run pytest tests/test_models.py -v                                # 単一ファイルのテストを実行
uv run pytest tests/test_watcher.py::TestClassName::test_name -v     # 単一テストを実行
```

## アーキテクチャ

[Textual](https://textual.textualize.io/) ベースの TUI で、[libtmux](https://libtmux.git-pull.com/) 経由で tmux を監視する。

**データフロー:**
1. `TmuxClient` が libtmux をラップし、セッション/ウィンドウ/ペインの階層を取得してペイン出力をキャプチャする
2. `TmuxWatcher` が一定間隔で `TmuxClient.poll()` を呼び出し、ペイン内容（ハッシュ比較・正規表現パターン）を分析して、状態変化や構造変化を `TmuxEvent` として emit する
3. `MuxpilotApp`（Textual の `App`）が `set_interval` で2秒ごとのポーリングループを駆動し、ブロッキングな `TmuxWatcher.poll()` を `asyncio.to_thread` で実行してウィジェットを更新する
4. ウィジェット（`TmuxTreeView`・`DetailPanel`・`StatusBar`）は純粋な表示層で、`TmuxTree` / `TmuxEvent` を受け取って描画するだけ

**`models.py` の主要な型:**
- `TmuxTree` → `SessionInfo` → `WindowInfo` → `PaneInfo`（tmux 状態のスナップショット）
- `PaneStatus` enum: `ACTIVE`, `IDLE`, `WAITING_INPUT`, `ERROR`, `COMPLETED`, `UNKNOWN`
- `PaneActivity`: ペインごとのコンテンツハッシュを保持して変化検出に使う
- `TmuxEvent`: 構造変化・ステータス変化の通知を運ぶ

## 規約

**TDD:** テストを先に書き、それから実装する。これはこのプロジェクトの絶対ルール。

**テストで本物の tmux は使わない:** libtmux は常に `unittest.mock` でモック化する。`tests/conftest.py` のファクトリ関数を使うこと:
- `make_pane()`, `make_window()`, `make_session()`, `make_tree()` — デフォルト値付きでモデルオブジェクトを生成
- `make_mock_client()` — `TmuxClient` として設定済みの `MagicMock` を返す

**Textual の非同期テスト**は `App.run_test()` を使う（pytest-asyncio）。`@pytest.mark.asyncio` でマークする。

**ステータス判定ロジック**（`TmuxWatcher._determine_status()`）:
- エラーパターンを最初に確認（直近10行）
- 最終行がプロンプトパターンに一致 → 直後なら `COMPLETED`、アイドル10秒超なら `WAITING_INPUT`
- コンテンツハッシュが10秒以上変化なし → `IDLE`
- 今回のポーリングでハッシュが変化 → `ACTIVE`

**自ペインはスキップ:** `TmuxWatcher.poll()` は muxpilot 自身が動いているペイン（`$TMUX_PANE` 環境変数で検出）を `ACTIVE` としてマークし、分析しない。

**`PaneInfo.display_label`** はツリー上のペイン表示の唯一の情報源。フォーマット: `{icon} [{command}] {親ディレクトリ}/{ディレクトリ}`

**libtmux のプロパティは `str | None` を返す** — モデルオブジェクト構築時は必ず `or ""` / `or 0` でガードすること（`tmux_client.py` のパターンを参照）。
