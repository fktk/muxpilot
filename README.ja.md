# muxpilot

![muxpilot](https://img.shields.io/badge/status-active-success.svg)
![python](https://img.shields.io/badge/python-3.12+-blue.svg)

**muxpilot** は、tmux のセッション・ウィンドウ・ペインを直感的にナビゲートするための TUI (Terminal User Interface) ツールです。

特に **AIエージェントのオーケストレーション** や、複数ペインで同時に動くタスクの管理を想定して設計されています。ペインの出力を監視し、「コマンド実行中」「指示待ち」「エラー発生」などの状態を自動で推定・可視化します。

[English README is here](./README.md)

## ✨ 主な機能

- **🌲 階層ツリー表示**: tmux の `Session → Window → Pane` 構造をツリー表示。
- **⌨️ キーボードナビゲーション**: Vimライクなキーバインド (`j`/`k`) で素早くペイン間を移動。
- **🔍 フィルタリング**:
  - `/`: 名前（セッション名、コマンド、パス等）による絞り込み
  - `w`: 入力待ち（プロンプト表示中）のペインのみ抽出
  - `e`: エラーが発生したペインのみ抽出
  - `c`: フィルタを解除して全表示
- **👀 ステータス監視**: 各ペインの出力を定期的にポーリングし、以下のステータスアイコンを自動付与します。

  | アイコン | ステータス | 検出条件 |
  |:---:|---|---|
  | `●` | ACTIVE | 今回のポーリングでペインの出力内容が変化した（コマンド実行中・ログ出力中など） |
  | `◌` | IDLE | プロンプトではないが、出力が一定時間（デフォルト10秒）以上変化していない |
  | `⏳` | WAITING | 最終行がプロンプトパターンに一致し、かつアイドル時間が閾値を超えている（ユーザーの入力待ち） |
  | `🔴` | ERROR | 直近10行にエラーパターン（`Traceback`, `Error:`, `FAILED` 等）が検出された |
  | `✅` | COMPLETED | 最終行がプロンプトパターンに一致し、かつアイドル時間が閾値以内（コマンドが完了した直後） |

  判定は **ERROR → COMPLETED / WAITING → IDLE → ACTIVE** の優先順で行われます。

- **🏷️ カスタムラベル**: `n` キーでセッション・ウィンドウ・ペインに任意の名前を付けられます。ラベルは `~/.config/muxpilot/config.toml` に永続化されます。
- **📋 詳細パネル**: 選択中のペイン内で実行されているコマンド、現在のディレクトリ、サイズなどの詳細情報を表示。

## 🚀 インストール & 起動

Pythonのパッケージマネージャ [uv](https://docs.astral.sh/uv/) を使用して起動できます。

### ローカル開発環境での起動

```bash
git clone https://github.com/fktk/muxpilot.git
cd muxpilot
uv run muxpilot
```

### どこからでも一時実行 (uvx)

インストール不要で、GitHubから直接実行することも可能です。

```bash
uvx --from git+https://github.com/fktk/muxpilot.git muxpilot
```

## ⚙️ 設定ファイル

`~/.config/muxpilot/config.toml` を作成すると、watcher の動作をカスタマイズできます：

```toml
[watcher]
prompt_patterns = ['[$>?]\s*$', 'In \[\d+\]: ']
error_patterns = ['(?i)Error|Exception|Traceback|FAILED|panic|Segmentation fault|FATAL']
idle_threshold = 10.0
```

- `prompt_patterns`: プロンプト検出用の正規表現リスト。**デフォルトを完全に置き換えます**。
- `error_patterns`: エラー検出用の正規表現リスト。**デフォルトを完全に置き換えます**。
- `idle_threshold`: アイドル判定までの秒数。

詳細は `config.example.toml` を参照してください。

## ⌨️ キーバインド

| キー | アクション |
|------|-----------|
| `↑` / `k` | カーソルを上に移動 |
| `↓` / `j` | カーソルを下に移動 |
| `Enter` | 選択したペインにジャンプ（muxpilot は裏で起動し続けます） |
| `a` | すべてのノードを折り畳み / 展開（トグル） |
| `r` | 情報の手動リフレッシュ |
| `/` | フィルタ入力のオン/オフ |
| `e` | エラー（🔴）ペインのみ表示 |
| `w` | 指示待ち（⏳）ペインのみ表示 |
| `c` | フィルタを解除して全表示 |
| `n` | 選択中のノードの名前を変更（カスタムラベル） |
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

muxpilot は FIFO（名前付きパイプ）`~/.muxpilot/notify` を監視しており、外部プロセスから任意のメッセージを送信できます。

```bash
echo "ビルド完了！" > ~/.muxpilot/notify
```

これにより、シェルスクリプトや CI ツールから muxpilot 上に通知を表示させることができます。

## 🛠 技術スタック

- [libtmux](https://libtmux.git-pull.com/) - tmux サーバーとの通信、階層データの取得、ペイン出力のキャプチャ
- [Textual](https://textual.textualize.io/) - 高度なTUIコンポーネント、非同期イベントループによるUI描画とポーリング

## 📄 License

ライセンスは未設定です。
