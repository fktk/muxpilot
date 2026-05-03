# muxpilot

![muxpilot](https://img.shields.io/badge/status-active-success.svg)
![python](https://img.shields.io/badge/python-3.12+-blue.svg)

**muxpilot** は、tmux のセッション・ウィンドウ・ペインを直感的にナビゲートするための TUI (Terminal User Interface) ツールです。

特に **AIエージェントのオーケストレーション** や、複数ペインで同時に動くタスクの管理を想定して設計されています。ペインの出力を監視し、「コマンド実行中」「指示待ち」「エラー発生」「アイドル」などの状態を自動で推定・可視化します。

[English README is here](./README.md)

## ✨ 主な機能

- **🌲 階層ツリー表示**: tmux の `Session → Window → Pane` 構造をツリー表示。セッションは `■`、ウィンドウは `□` の記号で識別します。
- **⌨️ キーボードナビゲーション**: Vimライクなキーバインド (`j`/`k`) で素早くペイン間を移動。
- **🔍 フィルタリング**:
  - `/`: 名前（セッション名、コマンド、パス等）による絞り込み
  - `a`: フィルタを解除して全表示
- **👀 ステータス監視**: 各ペインの出力を定期的にポーリングし、以下の4種類のステータスアイコンを自動付与します。

  | アイコン | ステータス | 検出条件 |
  |:---:|---|---|
  | **A** | ACTIVE | ペインの出力が変化した、またはプロンプト・エラー・アイドル以外の状態（コマンド実行中・ログ出力中など） |
  | **W** | WAITING | 最終行がプロンプトパターンに一致している（ユーザーの入力待ち） |
  | **E** | ERROR | 直近10行にエラーパターン（`Traceback`, `Error:`, `FAILED` 等）が検出された |
  | **I** | IDLE | 設定した閾値以上、出力の変化がない |

  判定は **ERROR → WAITING → IDLE → ACTIVE** の優先順で行われます。

- **🏷️ ペイン名の変更**: `n` キーで選択中のペインに名前を付けられます。これは tmux のネイティブなペインタイトルを変更するため、他の tmux クライアントでも反映されます。
- **📋 詳細パネル**: 選択中のペインで実行されているコマンド、フルコマンドライン、現在のディレクトリ、Git リポジトリ名とブランチ、サイズ、ステータス、アイドル時間、直近の出力行などの詳細情報を表示。

## 🚀 インストール & 起動

Pythonのパッケージマネージャ [uv](https://docs.astral.sh/uv/) を使用して起動できます。

### ローカル開発環境での起動

```bash
git clone https://github.com/fktk/muxpilot.git
cd muxpilot
uv run muxpilot
```

**tmux セッション外**で実行した場合、自動的に `muxpilot` という名前の新しい tmux セッションを作成してアタッチします。

### どこからでも一時実行 (uvx)

インストール不要で、GitHubから直接実行することも可能です。

```bash
uvx --from git+https://github.com/fktk/muxpilot.git muxpilot
```

## ⚙️ 設定ファイル

`~/.config/muxpilot/config.toml` を作成すると、muxpilot の動作をカスタマイズできます。リスト形式の項目は、指定すると**デフォルトを完全に置き換えます**（マージではありません）。

```toml
[app]
theme = "textual-dark"  # "textual-light", "nord", "gruvbox" など

[watcher]
poll_interval = 2.0       # ポーリング間隔（秒）
idle_threshold = 10.0     # この秒数以上出力がなければ IDLE とみなす
prompt_patterns = [
    '[$#>%]\\s*$',
    'In \\[\\d+\\]: ',
]
error_patterns = [
    '(?i)Error|Exception|Traceback|FAILED|panic|Segmentation fault|FATAL',
]

[ui]
tree_panel_max_width = 60  # ツリーパネルの最大幅（文字数）

[notifications]
poll_errors = true                     # tmux ポーリング失敗時にトーストを表示
waiting_trigger_pattern = "WAITING"    # FIFO 経由で WAITING ステータスを強制する正規表現
```

- `prompt_patterns`: プロンプト検出用の正規表現リスト。
- `error_patterns`: エラー検出用の正規表現リスト。
- `poll_interval`: tmux への更新確認間隔。
- `idle_threshold`: 出力が止まってから IDLE と判定するまでの秒数。
- `tree_panel_max_width`: 左側ツリーパネルの最大幅。
- `poll_errors`: `false` にすると「tmux poll failed」通知を抑制します。
- `waiting_trigger_pattern`: 外部 FIFO メッセージ内にペイン ID（例: `%1`）とこのパターンの両方が含まれる場合、そのペインを `WAITING` ステータスに強制します。

詳細は `config.example.toml` を参照してください。

## ⌨️ キーバインド

| キー | アクション |
|------|-----------|
| `↑` / `k` | カーソルを上に移動 |
| `↓` / `j` | カーソルを下に移動 |
| `Enter` | 選択したペインにジャンプ（muxpilot は裏で起動し続けます） |
| `/` | 名前フィルタ入力のオン/オフ |
| `a` | フィルタを解除して全表示 |
| `n` | 選択中のペインの名前を変更 |
| `x` | 選択中のペインを終了 |
| `?` | ヘルプを表示 |
| `q` | 終了 |

## 💡 おすすめの使い方：ダッシュボード運用（司令塔）

muxpilot は「**ダッシュボードとして常に起動させ続ける**」設計になっています。
Enter キーを押して他のペインにジャンプしても、muxpilot 自体は終了せずに裏でモニタリングを継続します。

**おすすめの画面構成**:
tmux の画面を分割し、左側（または上部）に muxpilot を常駐させます。
muxpilot から `Enter` で作業ペインに飛び、用事が済んだら tmux のショートカット（例: `Prefix + 左矢印` 等）で muxpilot のペインに戻ってくる、という司令塔のような使い方が最適です。

## 🔔 トースト通知

muxpilot は画面右下にトースト通知を表示します。ペインの追加・削除などの構造変化や、手動リフレッシュ時に自動で表示されます。

### 外部からの通知

muxpilot は FIFO（名前付きパイプ）`~/.config/muxpilot/notify` を監視しており、外部プロセスからメッセージを送信できます。

```bash
echo "ビルド完了！" > ~/.config/muxpilot/notify
```

メッセージはトースト通知として表示されます。さらに、設定で `waiting_trigger_pattern` を指定している場合、メッセージ内に **ペイン ID（例: `%1`）とパターンの両方** が含まれていれば、そのペインを `WAITING` ステータスに強制できます。例:

```bash
echo "%42 WAITING" > ~/.config/muxpilot/notify
```

## 🛠 技術スタック

- [libtmux](https://libtmux.git-pull.com/) - tmux サーバーとの通信、階層データの取得、ペイン出力のキャプチャ
- [Textual](https://textual.textualize.io/) - 高度なTUIコンポーネント、非同期イベントループによるUI描画とポーリング

## 📄 License

ライセンスは未設定です。
