# muxpilot

![muxpilot](https://img.shields.io/badge/status-active-success.svg)
![python](https://img.shields.io/badge/python-3.11+-blue.svg)

**muxpilot** は、tmux のセッション・ウィンドウ・ペインを直感的にナビゲートするための TUI (Terminal User Interface) ツールです。

特に **AIエージェントのオーケストレーション** や、複数ペインで同時に動くタスクの管理を想定して設計されています。ペインの出力を監視し、「コマンド実行中」「指示待ち」「エラー発生」などの状態を自動で推定・可視化します。

## ✨ 主な機能

- **🌲 階層ツリー表示**: tmux の `Session -> Window -> Pane` 構造をツリー表示。
- **⌨️ キーボードナビゲーション**: Vimライクなキーバインド (`j`/`k`) で素早くペイン間を移動。
- **🔍 フィルタリング**: 
  - `/`: 名前（セッション名、コマンド、パス等）による絞り込み
  - `w`: 入力待ち（プロンプト表示中）のペインのみ抽出
  - `e`: エラーが発生したペインのみ抽出
- **👀 ステータス監視**: 各ペインの出力を定期的にポーリングし、以下のステータスアイコンを自動付与します。
  - `●` ACTIVE (出力中)
  - `◌` IDLE (出力停止中)
  - `⏳` WAITING (プロンプトでの指示待ち)
  - `🔴` ERROR (エラーパターンの検出)
  - `✅` COMPLETED (コマンド終了)
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

## ⌨️ キーバインド

| キー | アクション |
|------|-----------|
| `↑` / `k` | カーソルを上に移動 |
| `↓` / `j` | カーソルを下に移動 |
| `Enter` | 選択したペインにジャンプ（muxpilotを終了しフォーカス移動） |
| `Space` | ツリーノードの展開 / 折り畳み |
| `r` | 情報の手動リフレッシュ |
| `/` | フィルタ入力のオン/オフ |
| `e` | エラー（🔴）ペインのみ表示 |
| `w` | 指示待ち（⏳）ペインのみ表示 |
| `a` | フィルタを解除して全表示 |
| `q` | 終了 |

## 💡 おすすめの使い方：tmuxポップアップ

muxpilot は、対象のペインにジャンプした際に自動で終了する設計になっています。
このため、tmux の `display-popup` 機能を使って画面中央にフローティング表示させる **「コマンドパレット」風の運用** が最も快適です。

`~/.tmux.conf` に以下の設定を追加してください。（パスは環境に合わせて変更してください）

```tmux
# Prefix + m で muxpilot をポップアップ表示
bind m display-popup -E -w 80% -h 80% "cd ~/projects/python/pymux && uv run muxpilot"
```

## 🛠 技術スタック

- [libtmux](https://libtmux.git-pull.com/) - tmux サーバーとの通信、階層データの取得、ペイン出力のキャプチャ
- [Textual](https://textual.textualize.io/) - 高度なTUIコンポーネント、非同期イベントループによるUI描画とポーリング

## 📄 License

MIT License
