# サイドバー自動非表示機能の設計

## 概要

ターミナルの幅が一定サイズ以下になった場合、詳細パネル（detail-panel / サイドバー）を自動的に非表示にする機能を追加する。閾値は `~/.config/muxpilot/config.toml` の `[ui]` セクションで変更可能とする。

## 背景・動機

狭いターミナルウィンドウで muxpilot を使用すると、ツリーパネル（左）と詳細パネル（右）が両方とも極端に細くなり、どちらも使いにくくなる。特にペイン一覧の可読性が著しく低下するため、幅が不足している場合はツリーパネルのみを最大限に使えるようにしたい。

## 設計詳細

### 1. 設定値の追加

`label_store.py` に以下を追加する：

- `get_sidebar_hide_threshold() -> int`
  - デフォルト値: `80`（カラム数）
  - 読み込み元: `config.toml` の `[ui].sidebar_hide_threshold`
  - 既存の `get_tree_panel_max_width()` と同様のパターンで実装する

### 2. 表示切り替えロジック

`app.py` の `MuxpilotApp` に以下を追加する：

- `on_resize` イベントハンドラ
  - Textual の `Resize` イベントはウィンドウサイズ変更時に発火する
  - `self.size.width <= threshold` を判定
  - `#detail-panel` の `styles.display` を `"none"` または `"block"` に切り替え
- `on_mount` にて、初回マウント時にも現在のサイズで判定を行い、初期状態を正しく設定する

### 3. CSS

既存の `CSS` において `#detail-panel` は `width: 1fr` で定義済み。`display: none` にすると Horizontal コンテナ内で DetailPanel がレイアウト計算から除外されるため、`#tree-panel` が自動的に全幅を占有する。追加の CSS 変更は不要。

### 4. 閾値の特殊扱い

- `sidebar_hide_threshold <= 0` の場合：自動非表示機能を無効とみなし、常に表示する
- `0` を明示的に設定することで、従来の挙動（常に両方表示）を維持できる

### 5. 非表示中の詳細パネル更新

非表示中も `TmuxTreeView` の選択変更イベントは発火し続ける。`UIOrchestrator` はそのまま `DetailPanel.show_pane()` 等を呼び出す。非表示中の Widget に対する update/clear/write は Textual で安全に無視されるか、内部状態のみ更新されるため、表示復帰時に最新情報が即座に反映される。追加の対応は不要。

## テスト計画

- `test_label_store.py`:
  - `get_sidebar_hide_threshold()` のデフォルト値が `80` であること
  - `config.toml` に `sidebar_hide_threshold = 120` と書いた場合に `120` を返すこと
  - `0` を設定した場合に `0` を返すこと
- `test_app_ui.py`:
  - アプリのサイズが閾値以下の `Resize` イベントをシミュレートした場合、`#detail-panel` の `display` が `"none"` になること
  - 閾値以上の `Resize` イベントをシミュレートした場合、`#detail-panel` の `display` が `"block"` に戻ること
  - 閾値が `0` の場合、どのサイズでも `display` が変わらないこと

## 変更対象ファイル

1. `src/muxpilot/label_store.py` — `get_sidebar_hide_threshold()` の追加
2. `src/muxpilot/app.py` — `on_resize` イベントハンドラの追加、設定値読み込み
3. `tests/test_label_store.py` — `get_sidebar_hide_threshold` のテスト追加
4. `tests/test_app_ui.py` — resize テスト追加
5. `config.example.toml` — 新しい設定値の例を追加（もし存在すれば）
