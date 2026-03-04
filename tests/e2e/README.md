# E2E 测试套件 — 麻将游戏

使用 Playwright 自动化浏览器，分别对港式麻将和大连穷胡进行端到端测试。
测试无需人工参与——服务器自动启动、AI 自动打完整局、浏览器自动验证结果。

## 目录结构

```
tests/e2e/
├── conftest.py           # fixtures：server / page / lobby_page
├── helpers.py            # 游戏流程辅助函数（run_all_ai_game, wait_for_game_over …）
├── page_objects.py       # LobbyPage / GamePage Page Object
├── test_hk_lobby.py      # 港式大厅测试（4 条）
├── test_hk_game.py       # 港式完整游戏流程测试（10 条）
├── test_dalian_lobby.py  # 大连大厅测试（3 条）
├── test_dalian_game.py   # 大连完整游戏流程测试（11 条）
├── requirements.txt      # Python 依赖
└── pytest.ini            # asyncio_mode=auto, timeout=300, pythonpath=.
```

---

## 安装

### 1. Python 依赖

```bash
# 建议在虚拟环境中安装
pip install -r tests/e2e/requirements.txt
```

`requirements.txt` 包含：`playwright>=1.44`、`pytest>=8`、`pytest-asyncio>=0.23`、`pytest-timeout>=2.3`、`httpx`、`websockets`

### 2. 安装 Chromium 浏览器内核

```bash
playwright install chromium
```

> **在受限系统上**（如 Cloud Run / Debian 无 sudo），需要先安装系统依赖：
> ```bash
> playwright install-deps chromium   # 需要 root 或 sudo
> ```
> 如果没有 sudo 权限，可在 Dockerfile 或 CI 环境的 root 阶段执行。

---

## 运行

```bash
# 全部 E2E 测试（无头模式，自动启动服务器）
cd /path/to/mahjong
pytest tests/e2e/ -v

# 只跑港式测试
pytest tests/e2e/test_hk_lobby.py tests/e2e/test_hk_game.py -v

# 只跑大连测试
pytest tests/e2e/test_dalian_lobby.py tests/e2e/test_dalian_game.py -v

# 只跑大厅类（快速冒烟，~6s）
pytest tests/e2e/test_hk_lobby.py tests/e2e/test_dalian_lobby.py -v

# 有界面调试（会弹出 Chromium 窗口）
pytest tests/e2e/ -v --headed

# 单条测试调试
pytest tests/e2e/test_hk_game.py::TestHKGameFlow::test_hk_game_completes -v --tb=long
```

> **预计运行时间**：全套约 20 分钟（每局 AI 全自动打完需 30–90 秒/局）

---

## 工作原理

### 服务器 fixture（session 级）

`conftest.py` 在**随机空闲端口**启动后端进程，注入加速环境变量：

| 变量 | 测试值 | 默认值 | 说明 |
|---|---|---|---|
| `MJ_AI_DELAY_MIN` | 0.05s | 0.2s | AI 出牌最短间隔 |
| `MJ_AI_DELAY_MAX` | 0.15s | 0.6s | AI 出牌最长间隔 |
| `MJ_CLAIM_TIMEOUT` | 1.5s | 30s | 声索窗口超时 |
| `MJ_AI_TAKEOVER_GRACE` | 2.0s | 20s | 断线后 AI 接管宽限 |

整个测试会话共用**同一个服务器进程**（session 级 fixture），每个测试函数各自新建 Chromium 页面（function 级）。

### 全 AI 局策略（`run_all_ai_game`）

游戏测试不操作浏览器出牌，采用**全 AI 自动完成**策略：

1. REST API 创建房间，以 `e2e_kick` 身份加入（非 `ai_player_` 前缀）
2. 开始游戏，剩余 3 座由 AI 自动填满
3. 短暂 WebSocket 连接触发服务端 `_run_ai_turn` 任务，断开
4. 2 秒后 `e2e_kick` 被 AI 接管（`AI_TAKEOVER_GRACE` 机制，仅对非 `ai_player_` 前缀生效）
5. 4 个 AI 全部就位，游戏自动跑完
6. 轮询 `/api/rooms` 直到 `status=ended`
7. 浏览器以 `e2e_kick` 身份重连 → 服务端发送 `game_over(is_reconnect=True)` → 结算弹窗出现

> **注意**：必须用非 `ai_player_` 前缀的 player_id 才能触发 AI 接管定时器，这是服务端的安全限制（防止 AI 玩家被误触发接管）。

---

## 测试覆盖

| 测试集 | 条数 | 验证内容 |
|---|---|---|
| `test_hk_lobby` | 4 | 大厅加载、港式标签显示、房间状态 API |
| `test_hk_game` | 10 | 游戏启动、港式 badge、结算零和、番型明细、翻牌、无宝牌 badge |
| `test_dalian_lobby` | 3 | 大连标签显示、API 字段、港式/大连共存 |
| `test_dalian_game` | 11 | 游戏启动、大连 badge、结算零和、荒庄流局（概率）、宝牌 badge、听牌标识 |
| **合计** | **28** | 27 passed, 1 skipped（荒庄概率测试） |

---

## 常见问题

### `libnspr4.so: cannot open shared object file`

缺少 Chromium 系统依赖，执行：
```bash
playwright install-deps chromium
```

### `ModuleNotFoundError: No module named 'helpers'`

`pytest.ini` 中需要 `pythonpath = .`，已配置。确保从 `tests/e2e/` 或项目根目录运行。

### 测试超时（`TimeoutError: All-AI game did not finish`）

- 大连游戏因不换听机制可能较慢，已设 120s 上限
- 港式游戏设 90s 上限
- 可在 `run_all_ai_game(..., max_wait=180.0)` 增大

### `test_dalian_draw_shows_draw_label` 被 skip

荒庄（流局）概率约 20%，连续 3 局均未触发则跳过，属正常现象。
