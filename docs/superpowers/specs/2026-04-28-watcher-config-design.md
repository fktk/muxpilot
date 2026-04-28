# Watcher Configuration Design

## 1. 概要
`TmuxWatcher` の状態検知（プロンプト待機、エラー検知）に使用される正規表現パターンを、ユーザーが外部設定ファイル（`~/.config/muxpilot/config.toml`）からカスタマイズ可能にする。

## 2. 設定ファイルの場所
* `~/.config/muxpilot/config.toml`

## 3. 設定形式
デフォルトのパターンにマージされる形式とする。

```toml
[watcher]
# デフォルトパターンにマージされる追加パターン
prompt_patterns = ["^CustomPrompt>\\s*$"]
error_patterns = ["CustomCriticalError"]
```

## 4. 実装詳細
* `muxpilot.watcher.TmuxWatcher.__init__` で設定ファイルをロードする。
* ファイルが存在しない場合やパースエラー時は警告を出力し、デフォルトパターンのみを使用する。
* 設定された文字列は `re.compile()` でコンパイルし、既存のリストに結合する。
* `tomllib` を使用する（Python 3.11+ 前提）。
