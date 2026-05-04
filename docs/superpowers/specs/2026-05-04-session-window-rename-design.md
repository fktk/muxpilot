# session/window リネーム対応（n キー）設計

## 概要

現在 `n` キーはペインのみリネーム可能。tree view で session / window ノードが選択されている場合も `n` キーでリネームできるように拡張する。

## 現状

- `PaneTitleManager`（`controllers.py`）がリネーム操作を管理
- `start()` / `finish()` / `cancel()` の3メソッド構成
- `start()` は `node_type == "pane"` の場合のみリネーム開始
- `finish()` は `TmuxClient.set_pane_title()` を呼び出し
- `app_actions.py` の `ActionHandler` が UI（Input 表示/非表示）を制御

## 変更点

### 1. `controllers.py` — `PaneTitleManager` → `NodeRenameManager`

クラス名を変更し、session / window もサポート。

```python
class NodeRenameManager:
    def start(self, node_data):
        node_type = ...
        if node_type == "pane":
            key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
            target_id = pane.pane_id
            return pane.pane_title
        elif node_type == "window":
            key = f"{session.session_name}.{window.window_index}"
            target_id = window.window_id
            return window.window_name
        elif node_type == "session":
            key = session.session_name
            target_id = session.session_id
            return session.session_name
        return None

    def finish(self, value):
        if not self._key or not self._client:
            return None
        if self._node_type == "pane":
            self._client.set_pane_title(self._target_id, value)
        elif self._node_type == "window":
            self._client.rename_window(self._target_id, value)
        elif self._node_type == "session":
            if not value:   # 空文字は無視（セッション名を空にできない）
                self._key = None
                self._target_id = None
                return None
            self._client.rename_session(self._target_id, value)
        key = self._key
        self._key = None
        self._target_id = None
        return key
```

### 2. `tmux_client.py` — 新規メソッド

```python
def rename_window(self, window_id: str, name: str) -> bool:
    server = libtmux.Server()
    try:
        server.cmd("rename-window", "-t", window_id, name)
        return True
    except Exception:
        return False

def rename_session(self, session_id: str, name: str) -> bool:
    server = libtmux.Server()
    try:
        server.cmd("rename-session", "-t", session_id, name)
        return True
    except Exception:
        return False
```

### 3. `app.py` / `app_actions.py` / `app_ui.py`

`PaneTitleManager` のインポート・参照をすべて `NodeRenameManager` に置き換え。

### 4. テスト

- `test_pane_title_manager.py` → `test_node_rename_manager.py` にリネーム
- pane の既存テストを維持
- session / window の `start()`/`finish()` テストを追加（空文字無視も含む）
- `test_app_rename.py` に session / window 選択時の統合テストを追加

## 空文字列の扱い

| ノード種別 | 空文字列送信時の挙動 |
|-----------|-------------------|
| pane      | `set_pane_title(id, "")` を呼び出す（現状維持） |
| window    | `rename_window(id, "")` を呼び出す（tmux の自動命名に戻る） |
| session   | 何もしない（キャンセルと同じ） |

## 影響範囲

- `src/muxpilot/controllers.py`
- `src/muxpilot/tmux_client.py`
- `src/muxpilot/app.py`
- `src/muxpilot/app_actions.py`
- `src/muxpilot/app_ui.py`
- `tests/test_pane_title_manager.py`
- `tests/test_app_rename.py`
