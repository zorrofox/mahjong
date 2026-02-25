# 麻将游戏 / Mahjong

基于浏览器的多人麻将游戏，支持 1–4 名真人玩家，空位由 AI 自动填补。

A browser-based multiplayer Mahjong game. Supports 1–4 human players per room; empty seats are filled by AI.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![Tests](https://img.shields.io/badge/tests-501%20passed-brightgreen) ![Tiles](https://img.shields.io/badge/tiles-Cangjie6%20SVG-orange)

---

## 功能特性 / Features

- 标准中国麻将规则（144 张牌，含花牌季牌）
- 实时多人对战（WebSocket）
- AI 自动填补空位，启发式出牌与声索决策；人类玩家可在游戏进行中加入并接管 AI 座位
- 声索优先级：胡 > 碰/杠 > 吃；加杠时支持搶杠胡（限声索赢牌）；有多口可吃时分别显示三张牌序列供玩家选择（如「吃 三四五」/「吃 四五六」）
- 自摸与荣和均支持；最低番数门槛可配置（当前 1 番，即任意合法手牌可胡）
- 七对（七對）为合法胡牌型，计 +3 番
- 声索窗口 30 秒倒计时，归零自动跳过
- **番数驱动筹码结算**：`unit = min(64, 2^(番数-1))`（1番=1,2番=2,3番=4…7番+=64）；庄家付/收 2×unit，闲家付/收 1×unit；荣和放炮全包（放炮者独付三人自摸份额之和）；杠即时结算（各家付 1 筹码）；跨局累计，初始 1000 筹码；结算弹窗显示本局筹码变化量（±N，绿色/红色）
- **胡牌番数详情**：游戏结束时展示本局达成的番型列表及合计番数（支持 16 种港式番型）；胡牌时语音播报类型（「胡！自摸！」/「胡！点炮！」/「胡！嶺上開花！」）；弹窗显示胡牌类型（自摸 Tsumo / 点炮 Ron / 嶺上開花 Lingshang）
- **港式麻将牌面**：Wikimedia Commons Cangjie6 斜视 3D SVG（全套 42 张，含花牌季牌），传统象牙底面配色
- 摸牌后自动选中刚抓到的牌，出牌按钮立即可用；**双击 / 双指点击手牌直接出牌**（桌面 `dblclick` + 移动端 `touchend` 时间差，合并选牌与打牌两步操作）
- 庄家（庄）徽标显示在对应玩家名旁；庄家赢则连庄，闲家赢或流局则换庄
- 手牌自动整理（条 → 饼 → 萬 → 风/字/花季）；**中央弃牌区按空间位置排列**：底部左格始终为自己（金色边框高亮），右为下家，上排为上家和对家
- 游戏结束后支持重开局（保留原房间人类玩家，筹码持续累计）；**多人场景**：只有庄家可点"再来一局"（非庄家显示"等待庄家重开…"），其他玩家收到新局 game_state 时弹窗自动关闭，消除竞态混乱
- 大厅显示各房间实时筹码余额；已结束的房间显示"Rejoin 重回"按钮
- **断线宽限期**：真实玩家 WebSocket 断开后，保留 20 秒宽限期（`AI_TAKEOVER_GRACE`）；宽限期内重连则无缝恢复操作，超时后 AI 才接管座位，避免移动端短暂网络波动导致立即被 AI 顶替
- **中文语音 + 程序化音效（全面统一，桌面 + iOS 均支持）**：所有动作均有语音 + 音效——出牌（脆响）、碰/吃/杠（各自专属音效）、胡（四层程序化锣声音效）、流局（双音下行）；本人与对手动作覆盖完全一致；零音频文件，全部由 Web Audio API 实时合成；声音优先级机制避免吃/碰乱序和牌名被跳过；操作按钮等待 TTS 播完后出现，音效与界面时序同步。**移动端实现**：iOS 强制要求 `AudioContext` 在用户手势中创建，WebSocket 回调中创建会进入 `suspended` 状态无声；采用共享 `AudioContext` 单例，首次 `touchstart/click` 时解锁，后台切换后自动 `resume()`，确保对手动作音效在 iOS 同样生效
- **流畅渲染**：差量 DOM 更新（手牌/弃牌堆/副露仅在内容变化时重建）；`active-turn` 焦点切换平滑过渡（CSS transition）；声索/结算弹窗淡入动画；所有文本守卫防止无意义重绘
- **移动端竖屏支持**：`top/bottom` 区域横跨全列（手牌/对面玩家铺满屏宽）；声索弹窗高度紧凑（牌面图+倒计时并排，按钮始终可见）；大厅房间表格横向滚动；侧边玩家显示庄标+筹码；`touch-action: manipulation` 消除 300ms 延迟；44px 触控目标
- 响应式绿毡牌桌界面（桌面 1024px+ 全功能；手机 375px 竖屏可玩）；`API_BASE` / `WS_BASE` 动态适配本地开发与生产环境（`wss://` 生产 WebSocket）

---

## 快速启动 / Quick Start

**本地开发**（依赖 Python 3.11+）

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

打开浏览器访问 [http://localhost:8000](http://localhost:8000)。

**生产部署（Google Cloud Run + IAP）**

```bash
# 构建推送镜像
IMAGE="us-central1-docker.pkg.dev/YOUR_GCP_PROJECT_ID/mahjong-repo/mahjong:latest"
docker build -t ${IMAGE} . && docker push ${IMAGE}

# 部署更新
gcloud run deploy mahjong --image=${IMAGE} --region=us-central1 --project=YOUR_GCP_PROJECT_ID
```

生产地址：`https://YOUR_CLOUD_RUN_URL`（需 Google 身份认证）
IAP 公网地址：`https://YOUR_APP_DOMAIN`（SSL 证书签发中）

---

## 项目结构 / Structure

```
├── backend/
│   ├── game/          # 游戏引擎（牌型、胡牌、状态机、AI、番数计算）
│   ├── api/           # FastAPI 路由 + WebSocket 处理
│   └── tests/         # 后端单元测试（311 tests）
├── frontend/
│   ├── js/            # 大厅 + 游戏客户端
│   ├── tiles/         # Cangjie6 港式麻将 SVG 牌面（42 张）
│   └── tests/         # 前端单元测试（111 tests）
└── tests/
    └── integration/   # REST + WebSocket 集成测试（79 tests）
```

---

## 运行测试 / Running Tests

**后端单元测试**
```bash
cd backend
pip install -r requirements-test.txt
pytest
```

**前端单元测试**
```bash
npm install
npm run test:coverage
```

**集成测试**
```bash
cd tests/integration
pip install -r requirements.txt
pytest -v
```

---

## 技术栈 / Tech Stack

| 层级 | 技术 |
|---|---|
| 后端 | Python 3.11 + FastAPI 0.111 + Uvicorn |
| 实时通信 | WebSocket（Starlette 内置） |
| 前端 | 原生 HTML5 + CSS3 + JavaScript |
| 牌面图片 | Wikimedia Commons Cangjie6 SVG（CC BY-SA 4.0） |
| 测试 | pytest + Vitest |

---

## 番数与结算 / Han & Chip Settlement

胡牌时自动计算番型，番数直接驱动筹码结算。

**番型（港式规则，16 种）**：

| 番型 | 番数 | 说明 |
|---|---|---|
| 基本分 | +1 | 始终计入 |
| 自摸 | +1 | 非荣和自摸 |
| 无花 | +1 | 无花牌/季牌 |
| 门清 | +1 | 无副露且**荣和** |
| 平胡 | +1 | 全顺子+对子 2-8+门清荣和 |
| 断幺 | +1 | 全部牌 2-8，无幺九风字 |
| 嶺上開花 | +1 | 杠后补摸牌胡（自摸专属） |
| 本命花 | +1/张 | 座位匹配的花/季牌 |
| 自风碰 / 圈风碰 | 各 +1 | 碰本座风牌 / 碰当前圈风牌 |
| 混幺九 | +3 | 每组均含幺九或风字 |
| 七对 | +3 | 七个不同对子 |
| 碰碰胡 | +3 | 四副全刻子 |
| 混一色 | +3 | 一色数牌+风字 |
| 小三元 | +5 | 两副字牌刻子+第三种字牌对子 |
| 小四喜 | +6 | 三副风牌刻子+第四风对子 |
| 清一色 / 字一色 | 各 +7 | 纯一色 / 全风字 |
| 大三元 | +8 | 三副字牌（中发白）刻子 |
| 大四喜 | +13 | 四副风牌（东南西北）刻子 |

> 最低起胡：1 番（任意合法手牌可胡）。可在 `game_state.py` 调整 `MIN_HAN`。

**筹码结算公式**：

    unit = min(64, 2^(番数-1))
      1番=1  2番=2  3番=4  4番=8  5番=16  6番=32  7番+=64

    ┌─────────────────────────────────────────────────────────┐
    │ 自摸（Tsumo）          Ron（荣和，放炮全包）            │
    │  闲家赢：庄付 2u          放炮者独付三人自摸份额之和    │
    │          闲×2 各 1u  →赢+4u  闲家赢：2u+1u+1u = 4u    │
    │  庄家赢：三闲各 2u   →赢+6u  庄家赢：2u+2u+2u = 6u    │
    └─────────────────────────────────────────────────────────┘

    杠钱：每次杠立即结算，三家各付 1 筹码（固定，与番数无关）
    初始筹码：每人 1000；结算弹窗显示本局变化量（±N）及庄家标识（庄）

---

## WebSocket 协议 / Protocol

连接地址：`/ws/{room_id}/{player_id}`

| 消息（客户端→服务器） | 说明 |
|---|---|
| `{"type": "discard", "tile": "BAMBOO_5"}` | 出牌 |
| `{"type": "pung"}` | 碰 |
| `{"type": "chow", "tiles": [...]}` | 吃 |
| `{"type": "kong", "tile": "..."}` | 杠 |
| `{"type": "win"}` | 声明胡牌 |
| `{"type": "skip"}` | 过 |
| `{"type": "restart_game"}` | 重开局（仅游戏结束后有效） |

| 消息（服务器→客户端） | 说明 |
|---|---|
| `{"type": "game_state", "state": {...}}` | 完整游戏状态（含 `cumulative_scores`、`round_number`） |
| `{"type": "claim_window", "tile": "...", "actions": [...], "timeout": 30}` | 声索窗口，含倒计时秒数 |
| `{"type": "game_over", ..., "han_breakdown": [...], "han_total": N, "win_ron": bool, "chip_changes": {...}, "dealer_idx": N, "cumulative_scores": {...}}` | 游戏结束，含番型/胡牌类型/本局筹码变化/庄家标识 |

详细文档见 [CLAUDE.md](CLAUDE.md)。
