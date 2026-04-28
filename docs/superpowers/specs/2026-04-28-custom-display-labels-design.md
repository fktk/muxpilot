# カスタム表示名（Custom Display Labels）設計書

## 概要

muxpilot のツリービューに表示されるセッション・ウィンドウ・ペインの名前を、ユーザーが自由に変更・永続化できる機能を追加する。

## 要件

- 全レベル（セッション・ウィンドウ・ペイン）で表示名を変更可能
- muxpilot 内部のみで管理（tmux 側の名前は変更しない）
- `~/.config/muxpilot/config.toml` に永続化
- TUI 上でインライン編集（`n` キー）
- 空文字で確定するとデフォルト名に戻る

## 設計

### 1. データモデル変更（`models.py`）

`PaneInfo`, `WindowInfo`, `SessionInfo` に `custom_label: str = ""` フィールドを追加する。

各 `display_label` プロパティは `custom_label` が空でなければそれを返す。空なら現行ロジックで生成する。

ペインの場合、カスタムラベル表示時もステータスアイコンを先頭に付ける: `f"{icon} {custom_label}"`

### 2. LabelStore（`label_store.py` 新規）

TOML ファイルを読み書きする単一責任クラス。

```python
class LabelStore:
    def __init__(self, config_path: Path | None = None):
        # デフォルト: ~/.config/muxpilot/config.toml

    def get(self, key: str) -> str:
        """キーに対応するカスタムラベルを返す。未設定なら空文字"""

    def set(self, key: str, label: str) -> None:
        """ラベルを設定し、即座にファイルに書き込む"""

    def delete(self, key: str) -> None:
        """カスタムラベルを削除（デフォルト表示に戻す）"""
```

### 論理キー形式

ドット区切りで階層を表現する:

| レベル | キー形式 | 例 |
|--------|----------|----|
| セッション | `session_name` | `"myproject"` |
| ウィンドウ | `session_name.window_index` | `"myproject.1"` |
| ペイン | `session_name.window_index.pane_index` | `"myproject.1.0"` |

### config.toml 形式

```toml
[labels]
"myproject" = "🚀 Main Project"
"myproject.1" = "Editor"
"myproject.1.0" = "vim server"
"myproject.1.1" = "test runner"
```

### 3. TUI 操作フロー

#### リネーム操作

1. ユーザーがツリーでノードを選択
2. `n` キー → フィルターバーと同じ位置にインライン入力欄が現れる（プレースホルダーに現在の表示名を表示）
3. Enter で確定 → `LabelStore.set()` → ツリー即時更新
4. 空文字で Enter → `LabelStore.delete()` → デフォルト名に復帰
5. Escape → キャンセル

#### App 層の変更（`app.py`）

- `MuxpilotApp` に `LabelStore` インスタンスを保持
- `action_rename()` メソッド追加（`n` キーバインド）
- リネーム入力にはフィルターと同じ `Input` ウィジェット方式を使用（ただし別の `Input` ウィジェット、または同じものをモード切替で再利用）
- `_do_refresh()` / `_poll_tmux()` で `TmuxTree` 構築後、App 層で `LabelStore` からラベルを適用する（`TmuxWatcher` はラベルを知らない）

#### ラベル適用ロジック

`_apply_labels(tree: TmuxTree, store: LabelStore)` ヘルパーを App 層に配置:

```python
def _apply_labels(tree: TmuxTree, store: LabelStore) -> None:
    for session in tree.sessions:
        label = store.get(session.session_name)
        if label:
            session.custom_label = label
        for window in session.windows:
            key = f"{session.session_name}.{window.window_index}"
            label = store.get(key)
            if label:
                window.custom_label = label
            for pane in window.panes:
                key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
                label = store.get(key)
                if label:
                    pane.custom_label = label
```

### 4. 影響範囲

- `models.py`: フィールド追加 + `display_label` 分岐
- `label_store.py`: 新規モジュール
- `app.py`: `LabelStore` 統合、`action_rename()`、ラベル適用
- `widgets/tree_view.py`: 変更なし（`display_label` を参照するだけ）
- `watcher.py`: 変更なし
- `tmux_client.py`: 変更なし

## テスト戦略

TDD に従い、テストを先に書く。

### test_label_store.py（新規）

- get/set/delete の基本動作
- ファイルが存在しない場合の初期化（ディレクトリ自動作成）
- ファイル永続化の検証（`tmp_path` フィクスチャ使用）
- セッション名にドットが含まれる場合のエッジケース（TOML のキーは引用符で囲む）

### test_models.py（追加）

- `custom_label` 設定時: 全レベルで `display_label` がカスタムラベルを返す
- `custom_label` 未設定時: 従来の動作を維持
- ペインのカスタムラベルにステータスアイコンが付くこと

### test_app.py（追加）

- `n` キーでリネーム入力欄が表示される
- リネーム確定後にツリーが更新される
- Escape でキャンセル
- 空文字で確定するとデフォルト名に戻る
