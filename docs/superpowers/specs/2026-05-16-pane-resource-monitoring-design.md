# Pane Resource Monitoring Design

## Problem

muxpilot ユーザーが各 tmux pane の CPU / メモリ使用量を知りたい。

## Design

### Data Collection (`resource_collector.py`)

新規モジュール `src/muxpilot/resource_collector.py` を追加。

```python
@dataclass
class ResourceInfo:
    cpu_percent: float
    memory_rss_kb: int

class ResourceCollector:
    _cache: dict[int, _ProcessCache]  # PID → prev_cpu_times + prev_time

    def get_resources(self, main_pid: int) -> ResourceInfo | None
```

- **psutil 拡張**: 既存の `psutil.Process(main_pid)` に対して `cpu_percent()` + `memory_info().rss` を呼ぶ
- **子プロセス**: `psutil.Process(main_pid).children(recursive=False)` で直近の子プロセスも合算
  - CPU%: メイン + 各子の `cpu_percent()` を合計
  - RSS: メイン + 各子の `memory_info().rss` を合算
- **前回値キャッシュ**: `cpu_percent()` は初回0になるため、`cpu_times() + time.time()` をキャッシュして自力で差分計算
  - 初回: キャッシュに保存し `None` を返す (次回から計算可能)
  - 2回目以降: 前回との差分 / elapsed time で CPU% を算出
- **エラーハンドリング**: `NoSuchProcess`, `AccessDenied`, `ZombieProcess` → `None` を返す
- **オーバーヘッド**: 最小限。選択中の pane 1つ + その子プロセスのみ

### Data Model (`models.py`)

`PaneInfo` に2フィールド追加:

```python
cpu_percent: float | None = None
memory_rss_kb: int | None = None
```

### Polling Integration (`watcher.py`)

`Watcher.poll()` に変更:
- 現在フォーカス中の pane (選択中ノード) の `pane_pid` を特定
- その PID に対してのみ `ResourceCollector.get_resources(pid)` を呼ぶ
- 結果を当該 `PaneInfo` に書き込む

`TimerCoordinator` の変更は不要（すでに `watcher.poll()` を定期呼び出し中）。

### UI Integration (`app_ui.py` → `detail_panel.py`)

`DetailPanel.show_pane()` にリソース行情報を追加:

```python
if pane.cpu_percent is not None:
    mem_mb = pane.memory_rss_kb / 1024 if pane.memory_rss_kb else 0
    text += f"- **CPU:** {pane.cpu_percent:.1f}%\n"
    text += f"- **Memory:** {mem_mb:.1f} MB\n"
```

データがない場合（権限不足・プロセス消失）は行を非表示。

### Key Decisions

| 項目 | 選択 |
|------|------|
| プラットフォーム | Linux only |
| 表示場所 | 詳細パネルのみ |
| 収集タイミング | 選択中の pane のみポーリングごとに収集（ハイブリッド） |
| PID取得 | tmux `#{pane_pid}`（既存） |
| 子プロセス | 直近の子まで合算 |
| ライブラリ | psutil（既存依存関係） |

### 非機能要件

- プロセス消失後のリソース情報は `None` に戻る（stale 表示を避ける）
- 子プロセスはポーリングごとに再取得（プロセス生成/終了に追従）
