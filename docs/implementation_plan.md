# tmux Session/Window/Pane Navigator TUI

AIエージェントのオーケストレーションを主なユースケースとする、tmux内TUIツール。session/window/paneの階層構造をツリー表示し、キーボード操作で対象paneに即座に移動できる。各paneの出力を監視し、エージェントの指示待ち・エラー停止・コマンド完了等をhooksなしで検出・通知する。

## ツール名の候補

> [!IMPORTANT]
> 以下から選んでください（または他の名前を指定）:

| 候補 | 由来 | イメージ |
|------|------|---------|
| **muxpilot** | mux + pilot | tmuxセッション群を操縦する司令塔 |
| **muxboard** | mux + dashboard | 全paneを俯瞰するダッシュボード |
| **muxhive** | mux + hive | 複数エージェントが働く巣（ハイブ） |
| **panoptix** | pan(全て) + optics(視) | 全ペインを見渡す全視眼 |
| **sessnav** | session + navigator | セッションナビゲーター |

## 技術スタック

| カテゴリ | 選定 | 理由 |
|---------|------|------|
| tmux操作 | **libtmux** | tmux server との抽象化。session/window/pane の階層取得、`select()` による移動、`capture_pane` による出力取得 |
| TUI フレームワーク | **Textual** | Python製の高機能TUI。Treeウィジェット、キーバインド、非同期対応。tmux pane内での動作実績あり |
| パッケージ管理 | **uv** | `uv init --lib` でプロジェクト作成、`uv run` / `uvx` で起動 |

## Proposed Changes

### プロジェクト構成

```
<project>/
├── pyproject.toml          # プロジェクト設定、依存関係、エントリポイント
├── README.md
├── src/
│   └── <package>/
│       ├── __init__.py
│       ├── __main__.py     # `python -m <package>` 対応
│       ├── app.py          # Textual App メインクラス
│       ├── tmux_client.py  # libtmux ラッパー（データ取得・操作）
│       ├── models.py       # データモデル（Session/Window/Pane情報）
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── tree_view.py    # tmux階層ツリーウィジェット
│       │   ├── detail_panel.py # 選択中paneの詳細表示
│       │   └── status_bar.py   # ステータスバー（イベント通知表示）
│       └── watcher.py      # イベント監視（ポーリング + capture-pane）
└── tests/
    ├── __init__.py
    ├── test_tmux_client.py
    └── test_models.py
```

---

### パッケージ設定

#### [NEW] pyproject.toml

```toml
[project]
name = "<project-name>"
version = "0.1.0"
description = "TUI tool for tmux session/pane navigation & AI agent orchestration"
requires-python = ">=3.11"
dependencies = [
    "libtmux>=0.40",
    "textual>=1.0",
]

[project.scripts]
<command> = "<package>.app:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/<package>"]
```

- ローカル: `uv run <command>`
- 配布: PyPI公開 or `uvx --from git+https://github.com/<user>/<project> <command>`

---

### tmux クライアント層

#### [NEW] tmux_client.py

libtmux をラップし、以下の機能を提供:

- **`get_tree()`**: 全 session → window → pane の階層データを取得
  - 各paneに `pane_current_command` と `pane_current_path` を付加
- **`navigate_to(pane_id)`**: 指定paneにフォーカスを移動
  - 異なるsession → `switch-client` → `select_window()` → `pane.select()`
- **`get_current_pane_id()`**: 自分自身のpane IDを取得（除外用）
- **`capture_pane_content(pane_id, lines)`**: paneの直近N行の出力を取得
- **`detect_changes(old_tree, new_tree)`**: 構造変更の検出（pane/window/session 追加・削除）

---

### データモデル

#### [NEW] models.py

```python
@dataclass
class PaneInfo:
    pane_id: str
    pane_index: int
    current_command: str
    current_path: str
    is_active: bool
    width: int
    height: int

@dataclass
class WindowInfo:
    window_id: str
    window_name: str
    window_index: int
    is_active: bool
    panes: list[PaneInfo]

@dataclass
class SessionInfo:
    session_name: str
    session_id: str
    is_attached: bool
    windows: list[WindowInfo]

@dataclass
class TmuxTree:
    sessions: list[SessionInfo]
    timestamp: float

@dataclass
class PaneActivity:
    """pane出力の変化を追跡"""
    pane_id: str
    last_content_hash: str      # 前回キャプチャのハッシュ
    last_line: str              # 最終行の内容
    idle_seconds: float         # 出力が変化していない秒数
    status: PaneStatus          # 推定ステータス

class PaneStatus(Enum):
    ACTIVE = "active"           # 出力中（ログ流れている等）
    IDLE = "idle"               # 出力停止中
    WAITING_INPUT = "waiting"   # プロンプト表示中（指示待ち）
    ERROR = "error"             # エラーパターン検出
    COMPLETED = "completed"     # コマンド完了（シェルプロンプト復帰）
```

---

### pane出力パターン検出（AIエージェント対応）

#### [NEW] watcher.py

エージェントのhooksを使わずに、pane出力のパターンからステータスを推定:

**検出ロジック**:

| ステータス | 検出方法 |
|-----------|---------|
| `ACTIVE` | 前回と出力が変化している |
| `IDLE` | 一定時間（設定可能）出力変化なし |
| `WAITING_INPUT` | 最終行がプロンプトパターンに一致（`$`, `>`, `?`, カスタムパターン） |
| `ERROR` | 出力に `Error`, `Exception`, `Traceback`, `FAILED` 等のパターン |
| `COMPLETED` | コマンド実行中→シェルプロンプト復帰を検出 |

```python
class TmuxWatcher:
    """pane出力をポーリングし、ステータス変化を検出"""
    
    def __init__(self, client: TmuxClient, interval: float = 2.0):
        self.client = client
        self.interval = interval
        self.activities: dict[str, PaneActivity] = {}
        # カスタムパターン（設定ファイルで拡張可能）
        self.prompt_patterns: list[re.Pattern] = [...]
        self.error_patterns: list[re.Pattern] = [...]
    
    async def poll(self) -> list[TmuxEvent]:
        """1回のポーリングでイベントを検出"""
        events = []
        tree = self.client.get_tree()
        
        for pane in all_panes(tree):
            content = self.client.capture_pane_content(pane.pane_id)
            old_activity = self.activities.get(pane.pane_id)
            new_activity = self._analyze(pane, content, old_activity)
            
            if old_activity and old_activity.status != new_activity.status:
                events.append(StatusChangeEvent(pane, old_activity.status, new_activity.status))
            
            self.activities[pane.pane_id] = new_activity
        
        return events
```

> [!NOTE]
> パターン検出は汎用的なデフォルトに加え、ユーザーが設定ファイル(`~/.config/<project>/patterns.toml`)でカスタムパターンを追加可能にする（Phase 4）。

---

### TUI アプリケーション

#### [NEW] app.py

**レイアウト**:
```
┌──────────────────────────────────────────────┐
│  <tool> - tmux agent orchestrator     [Help] │  ← Header
├──────────────────────┬───────────────────────┤
│                      │                       │
│   Session Tree       │   Detail Panel        │
│                      │                       │
│  ▸ 📦 session-1      │  Pane: %3             │
│    ▸ 🪟 0: bash      │  Command: python      │
│      ▶ %1 [vim] ~    │  Path: ~/project      │
│      ● %2 [agent] ⏳ │  Size: 80x24          │
│    ▸ 🪟 1: servers   │  Status: WAITING ⏳    │
│      ▶ %3 [node] 🔴  │  Idle: 45s            │
│  ▸ 📦 session-2      │                       │
│    ...               │                       │
│                      │                       │
├──────────────────────┴───────────────────────┤
│  ● 3 active  ⏳ 1 waiting  🔴 1 error       │  ← Status
└──────────────────────────────────────────────┘
```

**ステータスアイコン**:
- `●` 出力中（ACTIVE）
- `◌` アイドル（IDLE）
- `⏳` 指示待ち（WAITING_INPUT）
- `🔴` エラー検出（ERROR）
- `✅` 完了（COMPLETED）

**キーバインド**:

| キー | アクション |
|------|-----------|
| `↑` / `k` | カーソル上移動 |
| `↓` / `j` | カーソル下移動 |
| `Enter` | 選択したpaneに移動（TUI終了→pane切替） |
| `Space` | ツリーノード展開/折畳 |
| `r` | リフレッシュ |
| `/` | フィルタ（session/window名で絞り込み） |
| `e` | エラーのあるpaneだけ表示 |
| `w` | 指示待ちpaneだけ表示 |
| `a` | 全表示（フィルタ解除） |
| `q` / `Ctrl+C` | 終了 |
| `?` | ヘルプ |

---

## 実装フェーズ

### Phase 1: 基盤（MVP）
1. uv プロジェクト初期化
2. `models.py` — データモデル定義
3. `tmux_client.py` — libtmux ラッパー（情報取得 + pane移動 + capture_pane）
4. `app.py` + `tree_view.py` — ツリー表示 + Enter でpane移動
5. `uv run <command>` で起動確認

### Phase 2: UI強化
6. `detail_panel.py` — 詳細パネル
7. `status_bar.py` — ステータスバー
8. キーバインド完備（vim風 j/k, フィルタ `/`, ステータスフィルタ `e`/`w`/`a`）

### Phase 3: イベント監視 & パターン検出
9. `watcher.py` — ポーリング + capture-pane によるステータス推定
10. ツリー自動更新 + ステータスアイコン表示
11. イベント通知（ステータス変化時にハイライト）

### Phase 4: 仕上げ
12. カスタムパターン設定ファイル対応
13. エラーハンドリング（tmux未起動時等）
14. テスト追加
15. README 作成
16. `uvx` 起動対応の動作確認

## Verification Plan

### Automated Tests
```bash
uv run pytest tests/
uv run <command>  # TUI起動確認
```

### Manual Verification
- tmux 内の pane で起動し、全 session/window/pane が表示されること
- `Enter` で選択した pane にフォーカスが移ること
- pane出力のステータス（ACTIVE/IDLE/WAITING/ERROR）が正しく推定されること
- フィルタ機能（`/`, `e`, `w`）が動作すること
- 別ターミナルでpane追加/削除し、ポーリングで検出されること
