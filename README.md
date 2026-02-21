# 麻将游戏 / Mahjong

基于浏览器的多人麻将游戏，支持 1–4 名真人玩家，空位由 AI 自动填补。

A browser-based multiplayer Mahjong game. Supports 1–4 human players per room; empty seats are filled by AI.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![Tests](https://img.shields.io/badge/tests-349%20passed-brightgreen) ![Tiles](https://img.shields.io/badge/tiles-Cangjie6%20SVG-orange)

---

## 功能特性 / Features

- 标准中国麻将规则（144 张牌，含花牌季牌）
- 实时多人对战（WebSocket）
- AI 自动填补空位，启发式出牌与声索决策
- 声索优先级：胡 > 碰/杠 > 吃；加杠时支持搶杠胡（限声索赢牌）
- 自摸与荣和均支持；最低番数门槛可配置（当前 1 番，即任意合法手牌可胡）
- 七对（七對）为合法胡牌型，计 +3 番
- 声索窗口 30 秒倒计时，归零自动跳过
- **番数驱动筹码结算**：`unit = 2^(番数-1)`（7番封顶 64 单位）；庄家付/收双倍；荣和放炮全包；杠即时结算（各家付 1 筹码）；跨局累计，初始 1000 筹码
- **胡牌番数详情**：游戏结束时展示本局达成的番型列表及合计番数（支持 16 种港式番型）
- **港式麻将牌面**：Wikimedia Commons Cangjie6 斜视 3D SVG（全套 42 张，含花牌季牌），传统象牙底面配色
- 摸牌后自动选中刚抓到的牌，出牌按钮立即可用
- 庄家（庄）徽标显示在对应玩家名旁；庄家赢则连庄，闲家赢或流局则换庄
- 手牌自动整理（条 → 饼 → 萬 → 风/字/花季）
- 游戏结束后支持一键重开局（保留原房间人类玩家，筹码持续累计）
- 大厅显示各房间实时筹码余额；已结束的房间显示"Rejoin 重回"按钮
- **中文语音播报**：出牌念牌名（三万/七饼/东风…），碰/吃/杠/胡等动作实时语音；基于 Web Speech API，零音频文件
- 响应式绿毡牌桌界面

---

## 快速启动 / Quick Start

**依赖**：Python 3.11+

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

打开浏览器访问 [http://localhost:8000](http://localhost:8000)。

---

## 项目结构 / Structure

```
├── backend/
│   ├── game/          # 游戏引擎（牌型、胡牌、状态机、AI、番数计算）
│   ├── api/           # FastAPI 路由 + WebSocket 处理
│   └── tests/         # 后端单元测试（237 tests）
├── frontend/
│   ├── js/            # 大厅 + 游戏客户端
│   ├── tiles/         # Cangjie6 港式麻将 SVG 牌面（42 张）
│   └── tests/         # 前端单元测试（64 tests）
└── tests/
    └── integration/   # REST + WebSocket 集成测试（48 tests）
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

**番型（港式规则）**：

| 番型 | 番数 | 说明 |
|---|---|---|
| 基本分 | +1 | 始终 |
| 自摸 / 无花 | 各 +1 | 自摸/无花季牌 |
| 门清 | +1 | 无副露且**荣和**（平胡同） |
| 平胡 / 断幺 | 各 +1 | 全顺子荣和 / 全 2-8 |
| 嶺上開花 | +1 | 杠后补摸牌胡 |
| 本命花 | +1/张 | 收到座位匹配的花/季牌 |
| 自风碰 / 圈风碰 | 各 +1 | 碰本座位风牌 / 碰当前圈风牌 |
| 混幺九 | +3 | 全组含幺九或风字 |
| 七对 / 碰碰胡 / 混一色 | 各 +3 | — |
| 小三元 | +5 | — |
| 小四喜 | +6 | — |
| 清一色 / 字一色 | 各 +7 | — |
| 大三元 | +8 | — |
| 大四喜 | +13 |

**筹码结算公式**：

```
unit = min(64, 2^(番数-1))    每番翻倍，7番封顶 64 单位

自摸：闲家赢 = 庄付 2u + 闲×2 各付 1u = 4u 总收
      庄家赢 = 三闲各付 2u = 6u 总收
荣和：放炮者独付全额（等于自摸三人合计）
      闲家赢 4u，庄家赢 6u
杠钱：每次杠立即结算，三家各付 1 筹码给杠家（固定，与番数无关）
```

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
| `{"type": "game_over", ..., "han_breakdown": [...], "han_total": N, "cumulative_scores": {...}}` | 游戏结束，含番型详情与番数驱动结算后的累计筹码 |

详细文档见 [CLAUDE.md](CLAUDE.md)。
