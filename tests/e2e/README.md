# E2E 测试套件 — 麻将游戏

使用 Playwright 自动化浏览器，分别对港式麻将和大连穷胡进行端到端测试。

## 目录结构

```
tests/e2e/
├── conftest.py           # fixtures：server / browser / page
├── helpers.py            # 游戏流程辅助函数
├── page_objects.py       # LobbyPage / GamePage Page Object
├── test_hk_lobby.py      # 港式大厅测试（4条）
├── test_hk_game.py       # 港式完整游戏流程测试（10条）
├── test_dalian_lobby.py  # 大连大厅测试（3条）
├── test_dalian_game.py   # 大连完整游戏流程测试（11条）
├── requirements.txt      # 依赖
└── pytest.ini            # asyncio_mode=auto, timeout=120
```

## 安装

```bash
pip install -r tests/e2e/requirements.txt
playwright install chromium
```

## 运行

```bash
# 全部 E2E 测试（无头模式，自动启动服务器）
cd /path/to/mahjong
pytest tests/e2e/ -v

# 只跑港式测试
pytest tests/e2e/test_hk_lobby.py tests/e2e/test_hk_game.py -v

# 只跑大连测试
pytest tests/e2e/test_dalian_lobby.py tests/e2e/test_dalian_game.py -v

# 有界面调试
pytest tests/e2e/ -v --headed
```

## 工作原理

- `conftest.py` 在随机空闲端口启动后端，注入加速参数：
  - `MJ_AI_DELAY_MAX=0.15s`（AI 出牌极快）
  - `MJ_CLAIM_TIMEOUT=5.0s`（声索超时缩短）
- 游戏由 4 个 AI 玩家自动完成，测试等待结算弹窗
- 每个测试独立创建房间，互不干扰

## 测试覆盖

| 测试集 | 条数 | 验证内容 |
|---|---|---|
| `test_hk_lobby` | 4 | 大厅加载、港式标签显示、房间状态 |
| `test_hk_game` | 10 | 游戏启动、结算零和、番型明细、宝牌 badge 不显示 |
| `test_dalian_lobby` | 3 | 大连标签显示、API 字段、港式/大连共存 |
| `test_dalian_game` | 11 | 游戏启动、结算零和、荒庄流局、宝牌 badge、听牌标识 |
| **合计** | **28** | |
