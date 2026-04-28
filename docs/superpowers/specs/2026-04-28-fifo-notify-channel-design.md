# FIFO 通知チャネル設計

## 概要

muxpilot の通知を、名前付きパイプ (FIFO) 経由の外部信号トリガーに統一する。
外部プログラム（AI エージェント、スクリプト等）からのメッセージも、内部イベント（ステータス変化、フィルター操作等）も、同じ `NotifyChannel` を通じて `self.notify()` に到達する。

## 動機

- 外部プログラム（tmux 上の AI エージェント等）から muxpilot に通知を送りたい
- 内部通知と外部通知を統一的に扱いたい
- シェルから `echo "msg" > ~/.muxpilot/notify` だけで送信できる手軽さ

## アーキテクチャ

### NotifyChannel クラス (`src/muxpilot/notify_channel.py`)

```
外部プログラム ──→ FIFO (~/.muxpilot/notify) ──→ NotifyChannel._read_fifo_loop()
                                                          │
内部 (app.py, watcher events) ──→ NotifyChannel.send()    │
                                                          ↓
                                                   asyncio.Queue
                                                          │
                                                          ↓
                                              MuxpilotApp._check_notifications()
                                                          │
                                                          ↓
                                                  self.notify(message)
```

#### コンストラクタ

- `fifo_path: Path` — FIFO のパス（デフォルト: `~/.muxpilot/notify`）
- `queue: asyncio.Queue[str]` — 通知メッセージのバッファ

#### メソッド

- `start()` → FIFO を作成し、バックグラウンドで `_read_fifo_loop()` を開始
- `stop()` → 読み取りループを停止し、FIFO を削除
- `send(message: str)` → Queue にメッセージを直接追加（内部通知用）
- `receive() -> str | None` → Queue から非ブロッキングで取得（ポーリング用）
- `_read_fifo_loop()` → FIFO からの読み取りをブロッキングで行うループ（`asyncio.to_thread` で実行）

#### FIFO ライフサイクル

1. `start()` で `os.mkfifo()` を呼び出し（既存なら削除して再作成）
2. FIFO を読み取り専用で open し、1行ずつ読み取って Queue に put
3. FIFO の writer が閉じると EOF → re-open して再度待機（ループ継続）
4. `stop()` で `_running = False` にし、FIFO を unlink

#### エラーハンドリング

- FIFO 作成失敗時: ログ出力して FIFO 読み取り機能を無効化（`send()` は引き続き動作）
- 読み取りエラー時: ログ出力して再試行

### app.py の変更

#### on_mount()

```python
self._notify_channel = NotifyChannel()
await self._notify_channel.start()
self.set_interval(0.5, self._check_notifications)
```

#### _check_notifications()

```python
async def _check_notifications(self) -> None:
    while True:
        msg = self._notify_channel.receive()
        if msg is None:
            break
        self.notify(msg, timeout=5)
```

#### 既存 notify 呼び出しの置き換え

すべての `self.notify(...)` を `self._notify_channel.send(...)` に置き換える。
`_check_notifications()` が Queue を消費して `self.notify()` を呼ぶ。

例外: `_check_notifications()` 内の `self.notify()` はそのまま（最終出口）。

#### アプリ終了時

`on_unmount()` または `action_quit()` のオーバーライドで `self._notify_channel.stop()` を呼ぶ。

### 外部からの使い方

```bash
# 単発メッセージ
echo "ビルド完了" > ~/.muxpilot/notify

# スクリプトから
notify_muxpilot() { echo "$1" > ~/.muxpilot/notify; }
notify_muxpilot "テスト全件パス"
```

## テスト計画

### test_notify_channel.py (新規)

1. **FIFO ライフサイクル**: `start()` で FIFO が作成され、`stop()` で削除されること
2. **send/receive**: `send()` したメッセージが `receive()` で取得できること
3. **FIFO 読み取り**: FIFO に書き込んだメッセージが Queue に入ること
4. **複数メッセージ**: 複数の `send()` が順序通り `receive()` できること
5. **receive が空**: Queue が空の時 `receive()` が `None` を返すこと
6. **stop 後のクリーンアップ**: `stop()` 後に FIFO ファイルが存在しないこと

テストでは `tmp_path` フィクスチャを使い、実際の `~/.muxpilot` は使わない。

### test_app.py (更新)

- `NotifyChannel` をモック化
- 既存テストが壊れないよう `send()` 呼び出しを検証に切り替え

## ファイル構成

- `src/muxpilot/notify_channel.py` — 新規
- `src/muxpilot/app.py` — 変更（NotifyChannel 統合）
- `tests/test_notify_channel.py` — 新規
- `tests/test_app.py` — 更新
- `tests/conftest.py` — 必要に応じて NotifyChannel モックファクトリ追加
