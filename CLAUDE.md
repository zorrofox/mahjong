# 麻将游戏 (Mahjong Game) — 项目文档

> **语言约定**：请始终用中文回复用户。

## 项目概述

基于浏览器的多人麻将游戏，支持 1–4 名玩家共享一个房间，空位由 AI 自动填补。采用标准中国麻将规则，Python FastAPI 后端 + 原生 HTML/JS 前端，通过 WebSocket 实现实时通信。

---

## 快速启动

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

打开浏览器访问 `http://localhost:8000`。

---

## 项目结构

```
majiang/
├── CLAUDE.md                        # 本文档
├── package.json                     # 前端测试依赖（Vitest）
├── vitest.config.js                 # Vitest 覆盖率配置
├── backend/
│   ├── main.py                      # FastAPI 入口，挂载路由 + 静态文件
│   ├── requirements.txt             # Python 依赖
│   ├── requirements-test.txt        # 测试专用依赖（pytest、httpx 等）
│   ├── pytest.ini                   # pytest 配置（asyncio_mode、覆盖率）
│   ├── game/
│   │   ├── __init__.py
│   │   ├── tiles.py                 # 牌型枚举、144 张牌组、洗牌函数
│   │   ├── hand.py                  # 胡牌判断、组合检测、碰杠吃判断
│   │   ├── game_state.py            # GameState：牌局状态机、发牌、摸打、申报
│   │   ├── ai_player.py             # AI：启发式出牌、声索决策
│   │   └── room_manager.py          # RoomManager：房间生命周期、溢出逻辑
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                # REST 接口：列出/创建/加入/开始房间
│   │   └── websocket.py             # WebSocket 游戏事件处理、AI 自动操作
│   └── tests/                       # 后端单元测试（pytest）
│       ├── test_tiles.py            # 72 tests
│       ├── test_hand.py             # 78 tests
│       ├── test_game_state.py       # 71 tests
│       ├── test_ai_player.py        # 23 tests
│       ├── test_room_manager.py     # 28 tests
│       └── test_routes.py           # 13 tests
├── frontend/
│   ├── index.html                   # 大厅页：房间列表、创建/加入
│   ├── game.html                    # 游戏页：四方牌桌、手牌、操作按钮
│   ├── css/
│   │   └── style.css                # 绿毡主题样式、响应式布局
│   ├── js/
│   │   ├── lobby.js                 # 大厅逻辑：轮询房间列表
│   │   └── game.js                  # 游戏逻辑：WebSocket 客户端、渲染
│   ├── tiles/                       # Cangjie6 港式麻将 SVG 牌面（42 张）
│   │   ├── BAMBOO_1.svg .. BAMBOO_9.svg
│   │   ├── CIRCLES_1.svg .. CIRCLES_9.svg
│   │   ├── CHARACTERS_1.svg .. CHARACTERS_9.svg
│   │   ├── EAST.svg SOUTH.svg WEST.svg NORTH.svg
│   │   ├── RED.svg GREEN.svg WHITE.svg
│   │   ├── FLOWER_1.svg .. FLOWER_4.svg
│   │   └── SEASON_1.svg .. SEASON_4.svg
│   └── tests/                       # 前端单元测试（Vitest）
│       ├── game.test.js             # 76 tests
│       └── lobby.test.js            # 19 tests
└── tests/
    └── integration/                 # 集成测试（pytest + httpx）
        ├── conftest.py              # TestClient fixtures
        ├── test_rest_api.py         # 14 tests
        ├── test_websocket.py        # 12 tests（含 TestRestartGame）
        ├── test_claim_window.py     # 34 tests（声索窗口 + 多口吃牌 + 边张/坎张 + 碰后加杠）
        └── test_hand_order.py       # 7 tests（手牌排序验证）
```

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端框架 | Python 3.11 + FastAPI 0.111 |
| 实时通信 | WebSocket（Starlette 内置） |
| 状态管理 | 纯内存（dict，无数据库） |
| 前端 | 原生 HTML5 + CSS3 + JavaScript（无框架） |
| 服务器 | Uvicorn（ASGI） |
| 后端测试 | pytest 8 + pytest-cov + pytest-asyncio + httpx |
| 前端测试 | Vitest 1 + @vitest/coverage-v8 |

---

## 核心游戏规则实现

### 牌型（`backend/game/tiles.py`）

144 张标准麻将牌：
- **数牌**：万子/条子/筒子各 9 种，每种 4 张（共 108 张）
- **风牌**：东南西北各 4 张（共 16 张）
- **字牌**：中发白各 4 张（共 12 张）
- **花牌/季牌**：梅兰菊竹、春夏秋冬各 1 张（共 8 张）

牌以字符串表示，例如：`"BAMBOO_5"`、`"EAST"`、`"RED"`、`"FLOWER_1"`。

### 胡牌判断（`backend/game/hand.py`）

`is_winning_hand(tiles)` 使用**递归回溯**：
1. 枚举所有对子候选
2. 移除对子后，尝试从最小牌开始剥离刻子（三张相同）或顺子（三张连续同花色）
3. 若恰好剥完 4 组，则为胡牌

额外支持：七对子判断（7 个不同对子）。

### 游戏状态机（`backend/game/game_state.py`）

`GameState` 管理以下阶段循环：

```
drawing → discarding → claiming → (下一轮 drawing)
                                ↓
                             ended（有人胡牌或牌墙摸空）
```

关键设计：
- **花牌自动收取**：摸到花牌/季牌立即从牌墙后端补牌
- **杠后补牌**：明杠/暗杠后从牌墙后端补一张
- **声索窗口**：有人出牌后，其余所有玩家均有机会声索，优先级：**胡 > 碰/杠 > 吃**
- `to_dict(viewing_player_idx)` 序列化时隐藏其他玩家手牌

### AI 逻辑（`backend/game/ai_player.py`）

- **出牌**：为每张牌打分，优先打孤立牌、荣誉牌，保留已成对/成组的牌
- **声索决策**：永远声索胡牌；碰/杠在模拟声索后若进度分提升则声索；吃同理
- **进度评分**：已成副 +30，手中刻子 +25，对子 +15，相邻关系 +4，孤张 -5

### 房间管理（`backend/game/room_manager.py`）

- 每个房间最多 4 名人类玩家
- `join_room()` 若目标房间已满，自动创建新房间并加入（返回 `was_redirected=True`）
- `start_game()` 用 `ai_player_1..3` 填满空位，调用 `deal_initial_tiles()` 发牌

---

## API 接口

### REST 接口（`/api/...`）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/rooms` | 获取所有房间列表 |
| `POST` | `/api/rooms` | 创建新房间（可选 `name` 字段） |
| `POST` | `/api/rooms/{id}/join` | 加入房间，body: `{"player_id": "..."}` |
| `POST` | `/api/rooms/{id}/start` | 开始游戏（补 AI、发牌） |

### WebSocket 协议（`/ws/{room_id}/{player_id}`）

**客户端 → 服务器：**

```json
{"type": "start_game"}
{"type": "discard", "tile": "BAMBOO_5"}
{"type": "pung"}
{"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]}
{"type": "kong", "tile": "BAMBOO_5"}
{"type": "win"}
{"type": "skip"}
```

**服务器 → 客户端：**

```json
{"type": "game_state", "state": {...}}
{"type": "action_required", "player_idx": 0, "actions": ["discard"]}
{"type": "claim_window", "tile": "BAMBOO_5", "actions": ["pung", "skip"]}
{"type": "game_over", "winner_idx": 1, "winner_id": "player1", "scores": {...}}
{"type": "error", "message": "Invalid action"}
```

**声索窗口超时**：5 秒后未响应的玩家自动跳过。

**AI 自动操作**：AI 出牌延迟 0.5–1.0 秒（增强真实感），声索决策即时执行。

---

## 前端实现

### 大厅页（`frontend/index.html` + `lobby.js`）

- 从 `localStorage` 加载/生成持久化 `playerId`
- 每 3 秒轮询 `/api/rooms` 更新房间列表
- 点击「Join」调用 `/api/rooms/{id}/join`；若被重定向到新房间则弹出提示
- 跳转 `game.html?room={roomId}&player={playerId}`

### 游戏页（`frontend/game.html` + `game.js`）

布局（CSS Grid）：

```
┌──────────────────────────────────────┐
│         对面玩家（背面朝上）          │
│  左侧玩家  │  中央桌面  │  右侧玩家  │
│  （背面）  │  弃牌/墙数  │  （背面）  │
│         我的手牌（正面）              │
│  [出牌][碰][吃][杠][胡][过]           │
└──────────────────────────────────────┘
```

**牌面渲染系统**：

牌面使用 Wikimedia Commons **Cangjie6 斜视 3D SVG** 图片（CC BY-SA 4.0），存放于 `frontend/tiles/`，由 `TILE_SVG_MAP` 常量映射：

```js
const TILE_SVG_MAP = {
  BAMBOO_1: 'tiles/BAMBOO_1.svg',   // 索子 1–9
  CIRCLES_1: 'tiles/CIRCLES_1.svg', // 筒子 1–9
  CHARACTERS_1: 'tiles/CHARACTERS_1.svg', // 万子 1–9
  EAST: 'tiles/EAST.svg',  // 风牌
  RED: 'tiles/RED.svg',    // 字牌（中/發/白）
  FLOWER_1: 'tiles/FLOWER_1.svg',   // 花牌
  SEASON_1: 'tiles/SEASON_1.svg',   // 季牌
  // ...共 42 张
};
```

`makeTileEl()` 根据 `TILE_SVG_MAP` 生成 `<img class="tile-img">` 标签加载 SVG；SVG 图片自带象牙底面、3D 立体边框和传统图案（斜视角度展示条/饼/万/风字牌面）。`TILE_MAP` 保留文字映射表（供排序、标签显示等逻辑使用），与渲染分离。

| 牌型 | `TILE_MAP` 文字标签 | 渲染方式 |
|---|---|---|
| BAMBOO_1..9 | 一～九（B1..B9） | `tiles/BAMBOO_*.svg` 图片 |
| CIRCLES_1..9 | 一～九（C1..C9） | `tiles/CIRCLES_*.svg` 图片 |
| CHARACTERS_1..9 | 一～九（M1..M9） | `tiles/CHARACTERS_*.svg` 图片 |
| EAST/SOUTH/WEST/NORTH | 東南西北 | `tiles/*.svg` 图片 |
| RED/GREEN/WHITE | 中/發/白 | `tiles/*.svg` 图片 |
| FLOWER_1..4 / SEASON_1..4 | 梅蘭菊竹/春夏秋冬 | `tiles/*.svg` 图片 |

**牌面视觉风格**：
- Cangjie6 斜视 3D 风格：展示牌面正面 + 侧面，象牙底色，真实传统港式麻将质感
- 背面牌（对手手牌）：纯 CSS 45° 蓝色条纹，无图片
- 手牌 44×62px / 弃牌 26×36px / 对手 24×33px / 声索弹窗 70×98px
- hover 效果：`filter: drop-shadow`（正确作用于透明背景图片）
- selected 效果：金色 `drop-shadow` + `outline` 轮廓

**WebSocket 断线重连**：2 秒后自动重连。

---

## 代码规模统计

| 文件 | 行数 | 说明 |
|---|---|---|
| `game/game_state.py` | 994 | 核心状态机 |
| `game/ai_player.py` | 371 | AI 逻辑 |
| `game/hand.py` | 594 | 胡牌算法 + 番数计算 |
| `game/tiles.py` | 201 | 牌型定义 |
| `game/room_manager.py` | 244 | 房间管理 |
| `api/websocket.py` | 888 | WebSocket 处理 |
| `api/routes.py` | 102 | REST 接口 |
| `main.py` | 54 | 应用入口 |
| `frontend/js/game.js` | 1,146 | 游戏客户端（含 TILE_SVG_MAP + Cangjie6 渲染） |
| `frontend/js/lobby.js` | 194 | 大厅客户端 |
| `frontend/css/style.css` | 863 | 样式表 |
| `frontend/tiles/` | 42 SVG | Cangjie6 港式麻将牌面图片 |
| **业务代码合计** | **~5,651** | |
| `backend/tests/` | ~1,800 | 后端单元测试（285 tests） |
| `frontend/tests/` | ~550 | 前端单元测试（95 tests） |
| `tests/integration/` | ~1,120 | 集成测试（67 tests） |
| **测试代码合计** | **~3,470** | |

---

## 实现过程记录

本项目由 Claude Code 使用多 Agent 协作模式完成，分三个并行 Agent：

### Agent 1：`game-logic`（先行）
负责全部核心游戏引擎（`tiles.py`、`hand.py`、`game_state.py`、`ai_player.py`），无网络依赖，可独立测试。此 Agent 完成后 Agent 2 才启动（因后端需导入游戏模块）。

### Agent 2：`api-backend`（game-logic 完成后启动）
负责 FastAPI 服务、房间管理（`room_manager.py`）、REST 接口（`routes.py`）及 WebSocket 处理（`websocket.py`），读取 game 模块接口后实现集成。

### Agent 3：`frontend`（与 Agent 2 并行）
负责所有前端文件，基于 API 契约文档独立开发，无需等待后端完成。

### 集成验证（Coordinator 完成）
- `python3 -c "from game.tiles import build_deck; ..."` — 所有模块导入正常
- REST API 全流程测试（创建房间 → 加入 → 开始）返回正确结果
- Uvicorn 服务器启动、`http://localhost:8000` 返回 200、`game.html` 返回 200

---

## Bug 修复记录

### Bug 1：`player.hand` 类型不匹配导致 `.forEach is not a function`

**发现时间**：初版上线后首次运行
**错误信息**：
```
TypeError: (player.hand || []).forEach is not a function
    at window.renderMyHand (game.html:485)
    at renderBoard (game.js:264)
```

**根本原因**：前后端对 `player.hand` 字段的格式约定不一致。

- 后端 `game_state.py` 的 `to_dict()` 将手牌序列化为**对象**：
  - 己方手牌：`{"tiles": ["BAMBOO_5", ...], "hidden": false}`
  - 对手手牌：`{"hidden": true, "count": 13}`
- 前端 JS 所有地方都把 `player.hand` 当作**数组**直接调用 `.forEach`、`.length` 等。

**修复方案**：在 `game.js` 中新增两个归一化辅助函数，覆盖全部调用点：

```js
// 取手牌数组：己方返回 tiles[]，对手隐藏牌返回 []
function getHandTiles(player) {
  const h = player?.hand;
  if (!h) return [];
  if (Array.isArray(h)) return h;
  if (h.hidden) return [];
  return h.tiles || [];
}

// 取手牌数量：对手隐藏牌用 count 字段
function getHandCount(player) {
  const h = player?.hand;
  if (!h) return 0;
  if (Array.isArray(h)) return h.length;
  if (h.hidden) return h.count || 0;
  return (h.tiles || []).length;
}
```

**修改文件**：

| 文件 | 位置 | 改动 |
|---|---|---|
| `frontend/js/game.js` | 新增 | 添加 `getHandTiles()` / `getHandCount()` |
| `frontend/js/game.js` | `renderMyHand` | `player.hand \|\| []` → `getHandTiles(player)` |
| `frontend/js/game.js` | `renderOpponent` | `(player.hand \|\| []).length` → `getHandCount(player)` |
| `frontend/js/game.js` | `sendChow` | `player.hand \|\| []` → `getHandTiles(player)` |
| `frontend/js/game.js` | `sendKong` | `player.hand \|\| []` → `getHandTiles(player)` |
| `frontend/game.html` | 内联 `renderOpponent` 补丁 | 同上，改用 `getHandCount(player)` |
| `frontend/game.html` | 内联 `renderMyHand` 补丁 | 同上，改用 `getHandTiles(player).forEach` |

**附带修复**：`renderCenterTable` 中读取牌墙数量时由 `state.wall_count` 改为 `state.wall_remaining ?? state.wall_count`，与服务端实际字段名对齐。

---

### Bug 2：`room_update` 消息导致控制台警告

**发现时间**：Bug 1 修复后
**错误信息**：
```
Unknown message type: room_update   (game.js:213)
```

**根本原因**：服务端会向房间内所有 WebSocket 连接广播 `room_update` 消息（用于刷新大厅房间列表），但游戏页的 `handleServerMessage` switch 语句没有对应 case，落入 `default` 打印警告。

**修复方案**：在 `game.js` 的消息分发器中添加静默处理：

```js
case 'room_update':
  // 仅大厅需要处理，游戏页忽略即可
  break;
```

**修改文件**：`frontend/js/game.js` — `handleServerMessage`

---

### Bug 3：第二轮起操作按钮全部失效（游戏死锁）

**发现时间**：正常游玩第一轮出牌后
**现象**：人类玩家出牌后，轮到自己的第二个回合时，界面上没有任何可点击的按钮，游戏卡死。

**根本原因**：游戏状态机存在 `drawing`（摸牌）阶段，`get_available_actions()` 在该阶段返回 `["draw"]`。但：

1. 前端没有"摸牌"按钮
2. 后端 `_handle_message` 也没有处理 `{"type": "draw"}` 消息的分支

导致 `_run_ai_turn` 判断轮到人类玩家后发送 `action_required: ["draw"]` 便停止，而前端收到后无法渲染出任何有效按钮，游戏永久卡死。

**修复方案**：在 `websocket.py` 的 `_run_ai_turn` 中，当轮到人类玩家且处于 `drawing` 阶段时，**服务端自动代为摸牌**（与 AI 玩家行为一致），完成后再发送 `action_required: ["discard", ...]`：

```python
if not current_player.is_ai:
    if gs.phase == "drawing":
        # 自动摸牌，无需客户端发送 draw 消息
        drawn = gs.draw_tile(gs.current_turn)
        await _broadcast_game_state(room_id)
        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return
    # 进入 discarding 阶段，通知玩家选择出牌
    await _send_action_required(room_id, gs.current_turn)
    return
```

同时修复重连场景：玩家重新连接时若处于 `drawing` 阶段，同样走 `_run_ai_turn` 自动摸牌，而不是直接发 `action_required`。

**修改文件**：`backend/api/websocket.py` — `_run_ai_turn` 及 WebSocket 连接建立时的重连处理逻辑

**设计说明**：数字麻将的惯例是摸牌由系统自动完成，玩家只需决定出哪张牌。保留 `"draw"` 阶段作为内部状态机节点是正确的，但不应暴露为需要客户端响应的动作。

---

### Bug 4：每次 AI 出牌后人类回合耗时约 19 秒（严重 UX 问题）

**发现时间**：多轮测试中通过 WebSocket 计时发现
**现象**：人类玩家出牌后，等待 AI 完成三轮出牌再返回操作权，每次等待约 **19 秒**，游戏体验极差。

**根本原因**：每次 AI 出牌后，服务端会向人类玩家发送声索窗口（`claim_window`）。即使人类完全无法声索该牌（`actions=['skip']`），服务端仍会等待 `CLAIM_TIMEOUT = 5` 秒后才自动跳过。3 位 AI 每轮各出一张牌，共等待 **5s × 3 = 15s**，加上 AI 的模拟延迟（0.5–1s），合计约 19 秒。

**测试数据**：
```
# 修复前：每轮 19.2s，3 个声索窗口各等待约 6s
claim_window at t=1.5s actions=['skip']
claim_window at t=7.7s actions=['skip']
claim_window at t=14.2s actions=['skip']
Round time: 19.2s
```

**修复方案**：在 `_handle_claim_window` 中，于发送声索窗口消息之前，先检查人类玩家是否只有 `skip` 可选。若是，则**立即服务端代为跳过**，无需等待客户端响应：

```python
# 对只有 skip 可选的人类玩家立即自动跳过
for i, player in enumerate(gs.players):
    if i == discarder_idx or player.is_ai:
        continue
    available = gs.get_available_actions(i)
    if set(available) <= {"skip"}:
        gs.skip_claim(i)  # 立即跳过，不发 claim_window，不等待

# 仅对仍有真实操作选项的玩家发送声索窗口
if gs.phase == "claiming":
    await _send_claim_window(room_id, tile)
```

**修改文件**：`backend/api/websocket.py` — `_handle_claim_window`

**效果**：每轮等待时间从 **19.2s 降至 7.6s**。

---

### Bug 5：声索窗口向已自动跳过的玩家发送 `actions=[]` 空消息

**发现时间**：Bug 4 修复后测试
**现象**：前端仍收到 6 个 `claim_window` 消息（每轮应为 3 个），且所有消息的 `actions` 均为空列表 `[]`。

**根本原因**：Bug 4 的修复令人类玩家进入 `_skipped_claims` 集合后，`get_available_actions()` 返回 `[]`（空）。但 `_send_claim_window` 仍对所有非出牌方玩家发消息，包括已被自动跳过的人类玩家。

**修复方案**：在 `_send_claim_window` 中，跳过操作列表为空的玩家：

```python
actions = gs.get_available_actions(i)
if not actions:   # 无可操作项，不发送
    continue
```

**修改文件**：`backend/api/websocket.py` — `_send_claim_window`

**效果**：每轮等待从 **7.6s 进一步降至 4.5s**，前端零收到无效声索窗口消息。

---

### Bug 6：荣和（放铳胡牌）时手牌重复添加且得分未计算

**发现时间**：代码审查阶段（通过逐行追踪 `declare_win` 调用链发现）
**现象**：当人类玩家在声索阶段声明胡牌时，出现两个问题：
1. 最终胡牌手牌中该张牌出现**两次**（共 15 张）
2. 声索窗口未立即关闭时（有其他玩家尚未响应），胡牌者**得分为 0**

**根本原因**：`declare_win` 的声索阶段分支存在逻辑缺陷：

```python
# 原代码（错误）：
player.hand.append(tile)          # 1. 将胡牌加入手牌（用于验证）
if not is_winning_hand(...):
    player.hand.remove(tile)      # 验证失败才移除
    raise ValueError(...)
# 验证成功：tile 留在手牌中 ↑

self._check_claim_window_closed() # 可能触发 _resolve_claims
# _resolve_claims 中：
claimer.hand.append(discard_tile) # 2. 再次加入 → 手牌出现 15 张！

# pending 分支（窗口未关闭时）：
return {"score": ..., "pending": True}  # 直接返回，后续无 score 计算
# → player.score 永远不会被累加
```

**修复方案（三处改动）**：

1. **`declare_win`**：验证时使用手牌副本，不修改真实手牌：
```python
# 修复后：用副本验证，不污染真实手牌
effective_hand = player.hand_without_bonus() + [tile]
if not is_winning_hand(effective_hand):
    raise ValueError(...)
# 不再 append(tile) 到真实手牌
```

2. **`_resolve_claims`（"win" 分支）**：在真正解决声索时一并计算并累加得分：
```python
if claim_type == "win":
    claimer.hand.append(discard_tile)      # 唯一的一次添加
    self._finalize_win(claimer_idx, ...)
    score = self._calculate_score(...)
    claimer.score += score                 # 在此处统一计分
```

3. **`declare_win` 尾部**：当声索窗口立即关闭（`_resolve_claims` 已执行）时提前返回，避免重复调用 `_finalize_win` 和重复累加得分：
```python
if self.phase == "ended" and ron:
    return {"score": player.score, ...}  # 直接返回已计算的分数
```

**修改文件**：`backend/game/game_state.py` — `declare_win`、`_resolve_claims`

---

### Bug 7：`autoSelectChow` 标签解析错误导致吃牌自动选择永远失败

**发现时间**：前端单元测试建立后（测试覆盖了该函数）
**现象**：玩家点击「吃」按钮后，始终提示"无法自动选择吃牌"，无法完成吃牌操作。

**根本原因**：`TILE_MAP` 中数牌标签格式为 `"B5"`（花色字母在前，数字在后），但 `autoSelectChow` 使用 `.slice(0, -1)` 截取数字部分：

```js
// 错误：
const num = parseInt(info.label.slice(0, -1)); // "B5".slice(0,-1) = "B" → NaN
```

`parseInt("B")` 返回 `NaN`，导致后续所有数字比较均失败，函数始终返回 `null`。

**修复方案**：改用 `.slice(1)` 截去首位花色字母，保留数字部分：

```js
// 修复后：
const num = parseInt(info.label.slice(1)); // "B5".slice(1) = "5" → 5
```

**修改文件**：`frontend/js/game.js:615` — `autoSelectChow`

---

### Bug 8（UI 重构）：牌面显示为代码字符串而非传统汉字

**发现时间**：用户反馈（UI 可用性问题）
**现象**：手牌和弃牌区显示的是 `"1B"`、`"3C"`、`"7M"` 等内部代码字符串，而非传统麻将牌样式的汉字，视觉辨识度极差。

**根本原因**：`TILE_MAP` 中数牌的 `text` 字段直接使用阿拉伯数字字符串（`"1"`…`"9"`），花色仅以 `info.suit`（`'B'`/`'C'`/`'M'`）附在数字旁——两者均为英文内部标识符，不具备传统麻将的视觉语意。

**修复方案（三处改动）**：

1. **`TILE_MAP`**：数牌 `text` 改为中文数字（`'一'`…`'九'`），新增 `sub` 字段存储花色名（`'条'`/`'饼'`/`'萬'`）：
```js
const HANZI = ['一','二','三','四','五','六','七','八','九'];
m[`BAMBOO_${i}`]     = { text: HANZI[i-1], sub: '条', ... };
m[`CIRCLES_${i}`]    = { text: HANZI[i-1], sub: '饼', ... };
m[`CHARACTERS_${i}`] = { text: HANZI[i-1], sub: '萬', ... };
```

2. **`makeTileEl`**：改用 `.tile-main` + `.tile-sub` 两层 `<span>` 结构，取代原来的字符串拼接：
```js
if (info.sub) {
  el.innerHTML = `<span class="tile-main">${escapeHtml(info.text)}</span>
                  <span class="tile-sub">${escapeHtml(info.sub)}</span>`;
} else {
  el.innerHTML = `<span class="tile-main">${escapeHtml(info.text)}</span>`;
}
```

3. **`style.css`**：全面重设 `.tile` 视觉样式：
   - 象牙骨色渐变背景：`linear-gradient(150deg, #fffef5, #ede4c4)`
   - 3D 浮雕边框：亮色上/左（`#fff8e8`）+ 暗色下/右（`#9a7e38`）+ `box-shadow`
   - 背面牌改为 45° 条纹图案
   - 各区域（手牌/弃牌/对手/弹窗）独立设置 `.tile-main`/`.tile-sub` 字号
   - 引入 Noto Serif SC（Google Fonts）字体栈

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/js/game.js` | `TILE_MAP`（`text`+`sub`）、`makeTileEl`（HTML 结构） |
| `frontend/css/style.css` | `.tile`、`.tile-main`、`.tile-sub` 完整重写 |
| `frontend/game.html` | 新增 Noto Serif SC Google Fonts 链接 |
| `frontend/index.html` | 同上 |
| `frontend/tests/game.test.js` | 更新 `tileToDisplay` 断言以匹配新汉字 `text` 值 |

---

### Bug 9：玩家返回大厅再重连后游戏变全自动

**发现时间**：多轮测试（用户反馈）
**现象**：玩家从游戏页返回大厅，再点击加入同一房间后，游戏变为全自动——玩家的出牌、碰、吃、胡等操作全部被忽略，座位由 AI 接管。

**根本原因**：`websocket.py` 的 `finally` 断连块（~第 500 行）会将玩家座位标记为 `is_ai = True`，以便 AI 在断线期间代为操作。但重连处理逻辑中从未重置该标志，导致玩家重连后座位依然被识别为 AI。

```python
# 断连时（finally 块）
gs.players[pidx].is_ai = True  # ← 标记为 AI

# 重连时（原代码）
player_idx = _player_index(gs, player_id)
# ← 缺失：未重置 is_ai = False
state_dict = gs.to_dict(...)
```

**修复方案**：在 `websocket_endpoint` 重连处理中，注册连接后立即检查并重置 `is_ai`：

```python
if player_idx is not None and not player_id.startswith("ai_player_"):
    if gs.players[player_idx].is_ai:
        gs.players[player_idx].is_ai = False
        logger.info("Player %s reconnected; seat %d restored to human control", ...)
```

**修改文件**：`backend/api/websocket.py`（`websocket_endpoint` 函数，`_player_index` 调用后）

---

### Bug 10：手牌排序修复无效（game.html 内联函数覆盖）

**发现时间**：用户验收测试
**现象**：在 `game.js` 的 `renderMyHand` 中加入了排序逻辑，但玩家看到的手牌仍然乱序。

**根本原因**：`game.html` 第 477 行用 `window.renderMyHand = function(...)` 定义了一个内联版本，在运行时**完全覆盖**了 `game.js` 中的同名函数。内联版本没有排序逻辑，导致 `game.js` 中的修复成为死代码。

```html
<!-- game.html 第 477 行 —— 覆盖 game.js 的 renderMyHand -->
window.renderMyHand = function(player, playerIdx, state) {
  ...
  getHandTiles(player).forEach(tileStr => {  // ← 无排序，直接渲染
    ...
  });
};
```

**修复方案（两步）**：

1. **提取顶层函数**：在 `game.js` 中将排序逻辑提取为独立的 `sortHandTiles(hand)` 函数（返回副本，不修改原数组），供两处复用：
```js
const _SUIT_ORDER = { B: 0, C: 1, M: 2 };
function sortHandTiles(hand) {
  return [...hand].sort((a, b) => {
    const ia = TILE_MAP[a] || {}, ib = TILE_MAP[b] || {};
    const sa = ia.suit !== undefined ? _SUIT_ORDER[ia.suit] : 3;
    const sb = ib.suit !== undefined ? _SUIT_ORDER[ib.suit] : 3;
    if (sa !== sb) return sa - sb;
    return (ia.label || a).localeCompare(ib.label || b);
  });
}
```

2. **修复内联覆盖**：在 `game.html` 的内联 `window.renderMyHand` 中调用 `sortHandTiles()`：
```js
sortHandTiles(getHandTiles(player)).forEach(tileStr => { ... });
```

排序规则：条(B) → 饼(C) → 萬(M) → 风/字/花/季，同花色内按数字升序。

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/js/game.js` | 新增 `sortHandTiles()` 函数；`renderMyHand` 调用它；导出到 `_mahjongTestExports` |
| `frontend/game.html` | 内联 `window.renderMyHand` 改用 `sortHandTiles()` |
| `frontend/tests/game.test.js` | 新增 8 个 `sortHandTiles` 单元测试 |
| `tests/integration/test_hand_order.py` | 新增 7 个集成测试（服务端不排序的验证 + Python 复现 JS 排序算法） |

---

### Bug 11：有副露时无法胡牌（"win" 按钮从不出现）

**发现时间**：正常游玩（碰牌后尝试胡牌时发现）
**现象**：玩家已碰/吃/杠后，即使手牌构成胡牌型，界面上也不会出现"胡"按钮；即使强制发送 `{"type": "win"}` 也会收到 `error`。

**根本原因**：`get_available_actions` 和 `declare_win` 均只将 `player.hand_without_bonus()` 传给 `is_winning_hand`，完全忽略已声索的副露。

- 有 1 个副露（3 张碰牌已移出手牌）：`hand_without_bonus()` 仅剩 11 张
- `get_available_actions` 中检查 `len(effective_hand) == 14` → 11 ≠ 14 → 不添加 `"win"`
- `is_winning_hand(11 张)` 期望找到 4 组 + 1 对 → 凑不够 → 始终返回 False

**正确的"14 张牌"不变量**：

| 副露数 | 手牌 | 副露代表牌（每副 3 张，杠也取前 3） | 合计 |
|---|---|---|---|
| 0 | 14 | 0 | 14 |
| 1 | 11 | 3 | 14 |
| 2 | 8 | 6 | 14 |
| 3 | 5 | 9 | 14 |
| 4 | 2 | 12 | 14 |

杠为 4 张牌，但仅取前 3 张作为代表（`meld[:3]`），因为杠摸牌已补回第 4 张的手牌位置。

**修复方案**：在所有 4 处 `is_winning_hand` 调用前计算副露代表牌，并将其合并后传入：

```python
meld_tiles = [t for meld in player.melds for t in meld[:3]]
# 1. get_available_actions 自摸阶段：
if len(effective_hand) + len(meld_tiles) == 14 and is_winning_hand(effective_hand + meld_tiles):
    actions.append("win")

# 2. get_available_actions 声索阶段：
test_hand = effective_hand + [tile] + meld_tiles
if is_winning_hand(test_hand):
    actions.append("win")

# 3. declare_win 自摸：
if not is_winning_hand(effective_hand + meld_tiles):
    raise ValueError(...)

# 4. declare_win 荣和：
effective_hand = player.hand_without_bonus() + [tile]
if not is_winning_hand(effective_hand + meld_tiles):
    raise ValueError(...)
```

**修改文件**：`backend/game/game_state.py` — `get_available_actions`（2 处）、`declare_win`（2 处）

**新增测试**（`backend/tests/test_game_state.py`，5 个）：
- `test_self_draw_win_with_pung_meld`：有 1 副碰牌时自摸胡牌
- `test_self_draw_win_action_offered_with_melds`：有副露时 `"win"` 出现在可用操作中
- `test_ron_win_with_pung_meld`：有 1 副碰牌时荣和
- `test_ron_win_action_offered_with_melds`：有副露时声索阶段 `"win"` 出现
- （原有）各阶段胡牌基础路径保持 pass

---

### Bug 12：胡牌后无法重新开局

**发现时间**：正常游玩（游戏结束后点击"再来一局"时发现）
**现象**：游戏结束后，没有"再来一局"按钮；即使手动向后端发送 `{"type": "start_game"}`，也会收到 400 错误，因为 `room.status == "ended"` 不是 `"waiting"`。

**根本原因**：

1. `room_manager.start_game()` 要求 `room.status == "waiting"`，但游戏结束后 `_handle_game_over` 将其设为 `"ended"`，没有任何重置路径
2. 前端 game-over 弹窗只有"Close"和"Back to Lobby"两个按钮，没有"再来一局"按钮
3. WebSocket 消息处理器没有 `restart_game` 分支

**修复方案（三处改动）**：

**1. `backend/game/room_manager.py` — `start_game`**

允许从 "ended" 状态重启，自动重置 status：
```python
if room.status == "ended":
    room.status = "waiting"  # 允许重启
if room.status != "waiting":
    raise ValueError(...)
```

**2. `backend/api/websocket.py` — 新增 `restart_game` 消息处理**

```python
if msg_type == "restart_game":
    if room.status != "ended":
        await _send(ws, {"type": "error", "message": "Game has not ended yet."})
        return
    room_manager.start_game(room_id)  # 内部重置 ended→waiting→playing
    await _broadcast_game_state(room_id)
    await _broadcast_room_update()
    gs = room.game_state
    if gs.players[gs.current_turn].is_ai:
        asyncio.create_task(_run_ai_turn(room_id))
    else:
        await _send_action_required(room_id, gs.current_turn)
```

**3. 前端**

- `frontend/game.html`：在 game-over 弹窗中添加"Play Again 再来一局"按钮
- `frontend/js/game.js`：点击后先关闭弹窗，再通过 WebSocket 发送 `{type: "restart_game"}`

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/room_manager.py` | `start_game` 允许从 "ended" 重启 |
| `backend/api/websocket.py` | 新增 `restart_game` 消息处理分支 |
| `frontend/game.html` | 弹窗新增"Play Again 再来一局"按钮 |
| `frontend/js/game.js` | 按钮点击发送 `restart_game` WS 消息 |
| `tests/integration/test_websocket.py` | 新增 3 个集成测试（TestRestartGame） |

---

### Bug 13：点击「过」后游戏永久卡死（声索窗口无法关闭）

**发现时间**：正常游玩（点击声索窗口的「过」按钮后）
**现象**：人类玩家在声索窗口点击「Skip / 过」后，游戏画面停滞，不再推进到下一轮，弹窗消失但再也不会有任何新的操作提示。

**根本原因**（三处独立缺陷）：

**Bug 13a — 超时强制跳过时 `is_ai` 检查导致漏跳**

`_handle_claim_window` 的超时处理器在遍历 `_pending_claims` 时使用了 `not player.is_ai` 判断：

```python
# 原代码（有问题）：
for i, player in enumerate(gs.players):
    if not player.is_ai and i not in gs._skipped_claims:
        gs.skip_claim(i)
```

玩家断线时 `finally` 块会将 `player.is_ai` 置为 `True`（让 AI 接管）。若断线恰好发生在声索窗口期间，`is_ai == True` 的玩家会被超时循环跳过，其 `_pending_claims` 条目永远不会被清除，导致声索窗口永不关闭。

**Bug 13b — 超时后无兜底恢复路径**

超时处理器执行后即使声索窗口未能关闭（因 Bug 13a），代码仍会继续调用 `asyncio.create_task(_run_ai_turn(room_id))`。该任务发现 `gs.phase == "claiming"` 后立即返回，无任何恢复逻辑，游戏永久卡死。

**Bug 13c — 人类「过」后双重 `_run_ai_turn` 竞态**

`_handle_claim_window` 通过 `_wait_for_claim_window`（每 0.1 秒轮询一次）等待所有玩家响应。当人类点击「过」并关闭声索窗口后：

1. **skip 处理器**立即发现 `phase != "claiming"`，调用 `asyncio.create_task(_run_ai_turn)`
2. **`_wait_for_claim_window`** 在 ≤ 0.1 秒内也检测到 phase 变化，唤醒 `_handle_claim_window`，后者同样调用 `asyncio.create_task(_run_ai_turn)`

两个 `_run_ai_turn` 任务竞态执行，在时序敏感的情况下造成游戏状态混乱。

**修复方案**：

**1. 新增模块级标志 `_claim_window_active: set[str]`**

在 `websocket.py` 顶层新增集合，追踪当前正在运行 `_handle_claim_window` 协程的房间：

```python
_claim_window_active: set[str] = set()
```

**2. `_handle_claim_window` — 标志管理 + 超时修复 + 安全兜底**

```python
async def _handle_claim_window(room_id: str) -> None:
    ...
    _claim_window_active.add(room_id)
    try:
        ...
        # 超时后强制跳过所有仍 pending 的玩家，不再检查 is_ai
        except asyncio.TimeoutError:
            if gs.phase == "claiming":
                for i in list(gs._pending_claims):
                    if i not in gs._skipped_claims:
                        try:
                            gs.skip_claim(i)
                        except ValueError:
                            pass

        # 安全兜底：若 phase 依然是 claiming，再做一轮强制跳过
        if gs.phase == "claiming":
            for i in list(gs._pending_claims):
                if i not in gs._skipped_claims:
                    try:
                        gs.skip_claim(i)
                    except ValueError:
                        pass
    finally:
        _claim_window_active.discard(room_id)  # 无论如何都清除标志

    ...
    if gs.phase == "claiming":
        # 所有手段均失效，记录错误并返回，避免无限循环
        logger.error("Claim window could not be resolved in room %s; giving up.", room_id)
        return

    asyncio.create_task(_run_ai_turn(room_id))
```

**3. skip 处理器 — 使用 `_claim_window_active` 去重**

```python
if msg_type == "skip":
    ...
    gs.skip_claim(player_idx)
    ...
    if gs.phase != "claiming":
        # 声索窗口已关闭。仅在 _handle_claim_window 不再活跃时才启动新 _run_ai_turn，
        # 避免与 _wait_for_claim_window 唤醒路径竞态。
        if room_id not in _claim_window_active:
            asyncio.create_task(_run_ai_turn(room_id))
    else:
        # 窗口仍开（多人声索场景）：若无活跃处理器则重启一个
        if room_id not in _claim_window_active:
            asyncio.create_task(_handle_claim_window(room_id))
    return
```

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/api/websocket.py` | 新增 `_claim_window_active` 集合；`_handle_claim_window` 加标志管理、超时去 `is_ai` 检查、双重安全兜底；skip 处理器使用标志去重 |
| `tests/integration/conftest.py` | `_clear_state` fixture 增加 `_claim_window_active.clear()` |

---

### 功能增强 1：声索窗口 30 秒倒计时

**背景**：原声索窗口超时仅 5 秒，且前端无任何倒计时反馈，玩家往往在未看清牌面的情况下被自动跳过，体验较差。

**改动说明**：

**1. 超时时间延长（`backend/api/websocket.py`）**

```python
# 原值
CLAIM_TIMEOUT = 5.0
# 新值
CLAIM_TIMEOUT = 30.0
```

**2. `claim_window` 消息增加 `timeout` 字段**

```python
await _send(ws, {
    "type": "claim_window",
    "tile": tile,
    "actions": actions,
    "timeout": int(CLAIM_TIMEOUT),   # 新增
})
```

**3. 前端倒计时 UI（`frontend/game.html` + `frontend/js/game.js` + `frontend/css/style.css`）**

- 声索弹窗顶部新增倒计时栏：`自动跳过 / Auto-skip in 30s`
- 每秒递减，剩余 ≤10 秒时栏颜色变橙、数字变红并触发脉冲动画
- 归零时自动调用 `sendSkip()`，无需用户操作
- 玩家主动点击任意按钮（碰/吃/杠/胡/过）时立即清除定时器

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/api/websocket.py` | `CLAIM_TIMEOUT` 5→30；`claim_window` 消息新增 `timeout` 字段 |
| `frontend/game.html` | 声索弹窗内新增 `.claim-countdown-bar` 结构 |
| `frontend/js/game.js` | `handleClaimWindow` 透传 `timeout`；`showClaimOverlay` 接受 `timeout` 并启动 `_startClaimCountdown`；新增 `_startClaimCountdown`/`_clearClaimCountdown`/`_updateClaimCountdownDisplay`；`hideClaimOverlay` 调用 `_clearClaimCountdown` |
| `frontend/css/style.css` | 新增 `.claim-countdown-bar`、`.claim-countdown`、`.urgent` 状态及 `pulse-countdown` 动画样式 |

---

### 功能增强 2：跨局累计筹码结算（传统麻将规则）

**背景**：原计分系统只记录单局内的累计得分（`player.score`），每次重开局后归零，无法反映多局连续对战的真实胜负。

**规则实现**（传统中国麻将零和结算）：

| 胜负类型 | 结算方式 |
|---|---|
| 自摸（自己摸到胡牌）| 其余 3 家各付给胡牌者 `score` 筹码 |
| 荣和（放炮全包）| 放炮者独自付给胡牌者 `3 × score` 筹码；其余两家不付 |
| 流局（牌墙摸空）| 不结算，筹码不变 |

初始筹码：每人 **1000** 筹码（`INITIAL_CHIPS = 1000`）。

**后端改动**：

**1. `backend/game/game_state.py` — 记录胜利类型**

```python
# __init__ 中新增
self.win_ron: Optional[bool] = None          # True=荣和, False=自摸
self.win_discarder_idx: Optional[int] = None  # 放炮者索引（荣和时有效）

# _finalize_win 中赋值
self.win_ron = ron
self.win_discarder_idx = self.last_discard_player if ron else None
```

**2. `backend/game/room_manager.py` — Room 增加跨局字段**

```python
INITIAL_CHIPS = 1000  # 每个玩家槽位的初始筹码

@dataclass
class Room:
    ...
    cumulative_scores: dict = field(default_factory=dict)  # player_id → 当前筹码
    round_number: int = 0                                   # 本房间已进行的局数
```

`start_game` 中：
```python
room.round_number += 1
for pid in player_ids:
    room.cumulative_scores.setdefault(pid, INITIAL_CHIPS)  # 已有余额不覆盖
```

**3. `backend/api/websocket.py` — 结算逻辑 + 广播**

`_handle_game_over` 中按规则更新 `room.cumulative_scores`，并在 `game_over` 消息里附带：

```python
payload = {
    "type": "game_over",
    ...
    "cumulative_scores": dict(room.cumulative_scores),
    "round_number": room.round_number,
}
```

`_broadcast_game_state` 中也将 `cumulative_scores` 和 `round_number` 注入每个玩家的 `game_state` 消息，保证游戏中途随时可查。

**前端改动**：

**`frontend/game.html`**：
- 游戏结束弹窗积分表从 2 列（Player / Score）扩展为 3 列（玩家 / 本局得分 / 累计筹码），新增局数标签

**`frontend/js/game.js`**：
- 桌面玩家标签由 `Score: N` 改为 `筹码: N`（显示累计筹码余额）
- `handleGameOver` 透传 `cumulative_scores` 和 `round_number`
- `showGameOverModal` 按累计筹码降序排列积分表，胡牌者行高亮金色

**`frontend/game.html`（内联补丁）**：
- `renderOpponent` 和 `renderMyHand` 内联覆盖版同步改为显示筹码余额

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/game_state.py` | 新增 `win_ron`、`win_discarder_idx` 字段；`_finalize_win` 赋值 |
| `backend/game/room_manager.py` | 新增 `INITIAL_CHIPS` 常量；`Room` 新增 `cumulative_scores`、`round_number`；`start_game` 初始化/累加 |
| `backend/api/websocket.py` | 新增 `INITIAL_CHIPS` 导入；`_handle_game_over` 实现零和结算；`_broadcast_game_state` 注入筹码数据；`game_over` payload 增加两个字段 |
| `frontend/game.html` | 结算表 3 列化；新增局数标签；内联补丁改显示筹码 |
| `frontend/js/game.js` | `handleGameOver` / `showGameOverModal` 支持累计筹码；玩家标签改筹码显示 |
| `frontend/css/style.css` | 新增 `.winner-row` 金色高亮样式 |

---

### 功能增强 3：Cangjie6 港式麻将 SVG 牌面（UI 视觉升级）

**背景**：初版牌面使用纯 CSS + 汉字文本渲染（象牙底色 + 3D 浮雕边框），视觉效果与真实港式麻将差距较大。后续迭代中逐步尝试手绘内联 SVG（条子竹节、饼子同心圆），但与参考图片（维基百科 MJTiles_Fullset.png）仍有较大差距。

**最终方案**：换用 Wikimedia Commons **Cangjie6 斜视 3D SVG 牌面**（全套 42 张，CC BY-SA 4.0 授权）。

**资产获取方式**：

由于 Wikimedia `upload.wikimedia.org` 存在限速（HTTP 429），改从 `perthmahjongsoc/mahjong-tiles-svg` GitHub 仓库获取：

1. `git clone --depth 1` 仓库（文件为 Git LFS 指针）
2. 读取各指针文件中的 `oid sha256:` 字段
3. 调用 GitHub LFS Batch API 批量获取真实文件下载链接
4. 一次性下载全部 42 张 SVG（0 失败）

```python
LFS_API = "https://github.com/perthmahjongsoc/mahjong-tiles-svg.git/info/lfs/objects/batch"
# POST payload: {"operation": "download", "objects": [{oid, size}, ...]}
```

仓库目录结构映射到游戏牌名：

| 仓库目录 | 文件（Unicode） | 游戏键名 |
|---|---|---|
| `索/` | 🀐–🀘 | `BAMBOO_1–9` |
| `筒/` | 🀙–🀡 | `CIRCLES_1–9` |
| `萬/` | 🀇–🀏 | `CHARACTERS_1–9` |
| `番/` | 🀀–🀆 | `EAST/SOUTH/WEST/NORTH/RED/GREEN/WHITE` |
| `花/` | 🀢–🀩 | `FLOWER_1–4 / SEASON_1–4` |

**代码改动**：

**1. `frontend/js/game.js`**
- 新增 `TILE_SVG_MAP`（42 个键值对）
- `makeTileEl()` 改为生成 `<img class="tile-img" src="tiles/{KEY}.svg">`，加载失败时回退文字
- 删除旧的 `_makeBamboo1SVG`、`_makeBambooSVG`、`_makeCircleSVG`（约 250 行内联 SVG 生成器）
- Bug：改动期间出现两处 `makeTileEl` 函数声明（JS 后者优先，旧版生效），导致白底消失；修复方案：用 Python 脚本精确删除旧函数声明（188–434 行）

**2. `frontend/css/style.css`**
- `.tile` 去掉象牙色渐变背景、斜角边框、`box-shadow`（Cangjie6 SVG 自带 3D 效果）
- 新增 `.tile-img { object-fit: contain }`
- hover 改为 `filter: drop-shadow`；selected 改为金色 `drop-shadow` + `outline`
- `.tile-back`（背面牌）保留纯 CSS 蓝色斜纹，补回显式 `border`

**3. `frontend/tiles/`**（新增目录）
- 42 张 Cangjie6 斜视 3D SVG 文件，以游戏键名命名（`BAMBOO_1.svg` 等）

**视觉效果**：港式传统麻将斜视 3D 风格，象牙底面，竹节/圆圈/万字等图案清晰，与 Wikimedia 参考图片一致。

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/js/game.js` | 新增 `TILE_SVG_MAP`；`makeTileEl()` 改用 `<img>`；删除 ~250 行 SVG 生成器 |
| `frontend/css/style.css` | 去除手绘牌面 CSS；新增图片填充规则；更新 hover/selected 效果 |
| `frontend/tiles/` | 新增目录，存放 42 张 Cangjie6 SVG |

---

### 功能增强 4：胡牌番数详情（Han Breakdown）

**背景**：胡牌后仅显示"赢了"和筹码变动，玩家无法了解本局达成的番型及对应番数，缺乏传统麻将的计番乐趣。

**实现的番型**（港式规则简化版）：

| 番型 | 番数 | 触发条件 |
|---|---|---|
| 基本分 | +1 | 始终计入 |
| 自摸 | +1 | 非荣和（自己摸牌胡） |
| 无花 | +1 | 无花牌/季牌 |
| 门清 | +1 | 无任何副露（碰/吃/杠） |
| 平胡 | +1 | 四副全顺子 + 对子为 2–8 + 门清 |
| 断幺 | +1 | 全部牌为 2–8，无幺九风字 |
| 混幺九 | +2 | 每副及对子均含幺九或风字牌 |
| 七对 | +3 | 七个不同对子（特殊牌型） |
| 碰碰胡 | +3 | 四副全刻子 |
| 混一色 | +3 | 纯一花色 + 风字牌 |
| 清一色 | +7 | 纯一花色，无风字 |
| 字一色 | +7 | 全风牌或字牌 |
| 小三元 | +5 | 两副字牌刻子 + 对子为第三种字牌 |
| 大三元 | +8 | 三副字牌（中/發/白）刻子 |
| 小四喜 | +6 | 三副风牌刻子 + 对子为第四种风牌 |
| 大四喜 | +13 | 四副风牌（东南西北）刻子 |

**示例输出**（平胡自摸门清无花）：

```
番数详情 / Fan Breakdown
基本分  Base              +1
自摸    Tsumo             +1
无花    No Bonus Tiles    +1
门清    Concealed Hand    +1
平胡    Ping Hu           +1
断幺    All Simples       +1
合计: 6 番
```

**核心实现（`backend/game/hand.py`）**：

新增两个函数：

`decompose_winning_hand(concealed_tiles)` — 将手牌拆解为 `(pair, groups)` 结构：
- 支持七对特殊牌型
- 使用与 `is_winning_hand` 相同的回溯算法，返回实际分组而非 True/False
- 返回 `{'pair': str, 'groups': [{'type': 'pung'|'chow', 'tiles': [...]}], 'seven_pairs': bool}`

`calculate_han(concealed_tiles, declared_melds, flowers, ron)` — 计算番型：
- 接受手牌（含胡牌，不含花牌）、副露、花牌、是否荣和
- 内部调用 `decompose_winning_hand` 获取完整牌型结构
- 对 16 种番型逐一检测，互斥番型自然不会同时触发
- 返回 `{'breakdown': [{'name_cn', 'name_en', 'fan'}, ...], 'total': int}`

**数据流**：

```
declare_win() / _resolve_claims()
    └── _finalize_win(player_idx, winning_tile, ron)
            └── calculate_han(player.hand_without_bonus(),
                              player.melds, player.flowers, ron)
                    → self.han_breakdown, self.han_total

_handle_game_over()
    └── payload["han_breakdown"] = gs.han_breakdown
        payload["han_total"]    = gs.han_total

前端 handleGameOver(msg)
    └── showGameOverModal(..., msg.han_breakdown, msg.han_total)
            └── 渲染 .han-section 番型表格
```

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/hand.py` | 新增 `decompose_winning_hand()`、`calculate_han()` 及辅助常量/函数 |
| `backend/game/game_state.py` | 新增 `self.han_breakdown`、`self.han_total` 字段；`_finalize_win()` 调用 `calculate_han()` |
| `backend/api/websocket.py` | `game_over` payload 新增 `han_breakdown`、`han_total` 字段 |
| `frontend/game.html` | 游戏结束弹窗新增 `#han-breakdown-section` 番型表格区块 |
| `frontend/js/game.js` | `handleGameOver()` 透传番型数据；`showGameOverModal()` 渲染番型表格 |
| `frontend/css/style.css` | 新增 `.han-section`、`.han-table`、`.han-total-row` 样式；弹窗改为可滚动（`max-height: 90vh`） |

---

### 功能增强 5：番数驱动的筹码结算（含庄家与杠规则）

**背景**：功能增强 4 实现了番数展示，但筹码结算仍沿用旧的任意分值系统（基础 8 分 + 副露加分），与番数完全脱钩。本次将两者打通，并补充传统港式庄家双倍与杠钱规则。

**计分公式**：

```
unit = min(CHIP_CAP, 2 ^ (han_total - 1))    CHIP_CAP = 64（7 番封顶）

1番 → 1 chip   2番 → 2   3番 → 4   4番 → 8   5番 → 16   6番 → 32   7番+ → 64
```

**庄家规则**（player 0 固定为庄家）：
- 庄家付/收均为 **2×unit**，闲家付/收为 **1×unit**

**自摸（tsumo）结算**：

| 胡牌者 | 庄家付 | 每位闲家付 | 胡牌者总收 |
|---|---|---|---|
| 闲家 | 2×unit | 1×unit | 4×unit |
| 庄家 | — | 2×unit（×3人） | 6×unit |

**荣和（ron）结算**：

- 放炮者独付全额（相当于自摸时三人合计应付之和）
- 闲家胡：放炮者付 (2+1+1)×unit = **4×unit**
- 庄家胡：放炮者付 (2+2+2)×unit = **6×unit**
- 若庄家放炮给闲家：庄家作为放炮者独付 **4×unit**

**杠钱（kong payment）**：
- 每次杠即时结算，其余三家各付 **1 筹码** 给杠家（与最终番数无关）
- `record_kong_payment(konger_idx)` 将转账记入 `gs.kong_chip_transfers`
- 在 `_handle_game_over()` 优先于胡牌结算一并应用

**数据流（完整）**：

```
claim_kong() / _resolve_claims() 中的 kong 分支
    └── record_kong_payment(konger_idx)
            → kong_chip_transfers[konger] += 3
            → kong_chip_transfers[other]  -= 1  (×3)

_finalize_win(player_idx, winning_tile, ron)
    ├── calculate_han(...)  → han_breakdown, han_total
    └── player.score = han_total        ← 用于游戏结束界面"本局得分"列

_handle_game_over()
    ├── 应用 kong_chip_transfers（杠钱）
    ├── unit = min(64, 2^(han_total-1))
    ├── Ron:  discarder_pay = Σ _pay(i) for i ≠ winner
    └── Tsumo: each loser pays _pay(loser_idx)
            _pay(i) = 2×unit if i == dealer_idx else 1×unit
```

**删除旧系统**：
- `_calculate_score()` 方法从 `game_state.py` 中删除
- 旧测试类 `TestCalculateScore`（6 个测试）替换为 `TestHanBasedScore`（3 个新测试，验证 `player.score == han_total`、`record_kong_payment` 累加逻辑、`dealer_idx` 默认值）

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/game_state.py` | 新增 `dealer_idx`、`kong_chip_transfers` 字段；新增 `record_kong_payment()`；在 `claim_kong()` 和 `_resolve_claims()` 中调用；删除 `_calculate_score()`；`_finalize_win()` 设 `player.score = han_total` |
| `backend/api/websocket.py` | 新增 `CHIP_CAP = 64` 常量；`_handle_game_over()` 完全重写结算逻辑（杠钱先行 + 番数计算） |
| `backend/tests/test_game_state.py` | `TestCalculateScore` → `TestHanBasedScore`，新增 3 个测试 |

---

### 功能增强 6：摸牌自动选中 + 庄家标识显示

**摸牌自动选中**

摸牌后玩家须先点选一张牌才能出牌，体验不佳。本次让服务端告知前端刚摸到的牌，前端自动预选。

实现：
1. `game_state.py`：新增 `self.last_drawn_tile: Optional[str] = None`，在 `draw_tile()` 末尾赋值，在自摸杠和声索杠的补牌步骤中同样赋值
2. `websocket.py`：`_send_action_required()` 中，若可用操作包含 `"discard"` 且 `gs.last_drawn_tile` 非空，则在消息里附加 `"drawn_tile": gs.last_drawn_tile`
3. `game.js`：
   - `handleGameState()` 开始时清除 `selectedTile = null`（防止上一轮选择残留）
   - `handleActionRequired()` 收到含 `"discard"` 的消息且有 `msg.drawn_tile` 时，自动在 `.my-hand` 中找到对应 `.tile` 元素并调用 `selectTile()`，高亮上浮、出牌按钮立即可用

**庄家标识显示**

牌桌上无法判断谁是庄家，影响出牌策略判断。

实现：
1. `game_state.py`：`to_dict()` 返回字典新增 `"dealer_idx": self.dealer_idx`
2. `game.js`：`renderMyHand()` 和 `renderOpponent()` 中，若 `state.dealer_idx === playerIdx`，在玩家名后插入 `<span class="dealer-badge">庄</span>` 徽标
3. `style.css`：新增 `.dealer-badge` 样式（金色背景、深色文字、圆角小方块）

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/game_state.py` | 新增 `last_drawn_tile` 字段；三处赋值（`draw_tile`、自摸杠补牌、声索杠补牌）；`to_dict()` 新增 `dealer_idx` |
| `backend/api/websocket.py` | `_send_action_required()` 附加 `drawn_tile` 字段 |
| `frontend/js/game.js` | 摸牌预选逻辑；新游戏状态时清除 `selectedTile`；两处玩家标签加庄家徽标 |
| `frontend/css/style.css` | 新增 `.dealer-badge` 样式 |

---

### 功能增强 7：庄家轮换

**背景**：庄家（dealer_idx）此前写死为 player 0，且不会跨局更换，与传统麻将规则不符。

**规则**：
- 庄家赢牌（无论自摸或荣和）→ **连庄**，下局仍为庄家
- 闲家赢牌或流局（没有赢家）→ **换庄**，下局由下一个座位（顺时针 +1）担任庄家

**实现**：

1. `room_manager.py`：`Room` 新增 `dealer_idx: int = 0` 字段，跨局持久化，`start_game()` 将其传给 `GameState(dealer_idx=room.dealer_idx)`

2. `game_state.py`：`__init__` 新增 `dealer_idx: int = 0` 参数；`deal_initial_tiles()` 将 14 张牌发给 `self.dealer_idx` 座位（而非写死的 0），初始回合 `current_turn` 也从庄家开始

3. `websocket.py`：`_handle_game_over()` 在结算后更新 `room.dealer_idx`：

```python
if winner_idx is not None and winner_idx == gs.dealer_idx:
    pass  # 庄家赢 — 连庄
else:
    room.dealer_idx = (gs.dealer_idx + 1) % len(gs.players)  # 换庄
```

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/room_manager.py` | `Room` 新增 `dealer_idx` 字段；`start_game()` 透传给 `GameState` |
| `backend/game/game_state.py` | `__init__` 接受 `dealer_idx` 参数；`deal_initial_tiles()` 按庄家座位发牌 |
| `backend/api/websocket.py` | `_handle_game_over()` 实现连庄/换庄逻辑 |

---

## 港式规则修正记录

基于代码全面 review 发现的规则偏差，按严重程度依次修复。

### 规则修正 #1：七对（七對）胡牌启用

**问题**：`is_winning_hand` 中七对判断被注释掉，持有七对的玩家永远无法胡牌。

**修复**（`backend/game/hand.py`）：取消注释 `_is_seven_pairs` 调用：
```python
# 七对 (七對) — 标准港式规则
if _is_seven_pairs(sorted_tiles):
    return True
```
`calculate_han` 已正确为七对手牌计算 +3 番，同时支持七对版清一色/混一色/字一色组合。

**新增测试**（`TestSevenPairsWinningHand`，4 个）：七对合法性、全风字七对、四张同牌不合法、`calculate_han` 给 +3 番。

---

### 规则修正 #2：平胡（Ping Hu）仅限荣和

**问题**：平胡在自摸时也被授予，港式规则要求只能荣和时计平胡。

**修复**（`backend/game/hand.py`）：在平胡条件上增加 `and ron`：
```python
if (all_chows and not declared_melds and _h_is_simple(pair_tile) and ron):
    add('平胡', 'Ping Hu (All Sequences)', 1)
```

**新增测试**（`TestPingHuRonOnly`，2 个）：荣和时给平胡、自摸时不给平胡但给自摸。

---

### 规则修正 #3：混幺九（混幺九）检测修正

**问题**：使用 `any()` 检查每组"含一张幺九"，导致 [1,2,3] 这类含中间牌的顺子误判通过。

**修复**（`backend/game/hand.py`）：`any()` → `all()`，要求组内每张牌均为幺九或风字：
```python
if (all_groups
        and all(all(_h_is_terminal_or_honor(t) for t in g['tiles']) for g in all_groups)
        and _h_is_terminal_or_honor(pair_tile)):
    add('混幺九', 'Mixed Terminals & Honors', 2)
```

**新增测试**（`TestHunYaoJiu`，2 个）：全幺九碰牌合法、含中间牌组合不合法。

---

### 规则修正 #10：庄家荣和筹码公式修正

**问题**：`_pay` 函数当庄家赢时，由于庄家是赢家被排除在求和范围外，三位闲家每人只付 `1×unit`（应为 `2×unit`），导致庄家荣和仅收 `3×unit` 而非正确的 `6×unit`。

**修复**（`backend/api/websocket.py`）：`_pay` 增加赢家身份判断：
```python
def _pay(payer_idx: int) -> int:
    if winner_idx == dealer_idx:
        return 2 * unit  # 庄家赢：每位失家（均为闲家）付双倍
    return 2 * unit if payer_idx == dealer_idx else unit
```

**新增测试**（`TestRonChipFormulaDealerWin`，5 个）：庄家荣和收 6u、闲家荣和收 4u、庄家自摸收 6u、闲家自摸收 4u、番数缩放。

---

### 规则修正 #13：最低番数起胡门槛（MIN_HAN）

**问题**：任意合法牌型均可胡牌，港式严格赛事规则要求合计番数 ≥ 3 才可胡。

**实现**（`backend/game/game_state.py`）：新增常量 `MIN_HAN`，在三处执行最低番数检查：
- `get_available_actions()`：番数不足时不显示"胡"按钮
- `declare_win()`：番数不足时抛出 `ValueError`
- `_resolve_claims()`：番数不足时拒绝声索并推进至下一轮

**调整历史**：
- 初始设为 `MIN_HAN = 3`（港式赛事规则）
- **后回退至 `MIN_HAN = 1`**（任意合法手牌可胡）——因为 `MIN_HAN = 3` 过于严格，导致大量典型日常手牌无法胡牌（例：荣和 + 有副露 + 有花牌 = 仅基本分 1 番；荣和 + 有副露 + 无花牌 = 2 番），人类玩家几乎不可能满足 3 番门槛，而 AI 随机碰到复杂手牌才能胡。港式日常打法通常采用「最低 1 番」（任意结构合法即可胡）。

**当前值**：`MIN_HAN = 1`（可在 `game_state.py` 中调整为 3 以启用严格赛事规则）

**新增测试**（`TestMinimumFanRequirement`，4 个）：常量值 ≥ 1、低番手牌在 MIN_HAN 以上时跳过、高番手牌被接受、七对满足最低番数。

---

### 规则修正 #6/#7：加杠（加槓）与搶杠胡

**问题**：摸到第 4 张与已碰副露相同的牌时，无法将碰升级为杠；且加杠时其余玩家无机会搶杠胡。

**加杠实现**（`backend/game/game_state.py`）：

`claim_kong()` 在 4 张暗杠检查之前，优先检测延伸碰牌条件（手中有 1 张与已声明碰牌相同的牌）：
```python
extend_meld_idx = next(
    (i for i, m in enumerate(player.melds)
     if len(m) == 3 and m[0] == m[1] == m[2] == tile),
    None,
)
if extend_meld_idx is not None and player.hand.count(tile) >= 1:
    player.hand.remove(tile)
    player.melds[extend_meld_idx].append(tile)   # 碰(3张) → 杠(4张)
    # 设置搶杠声索窗口...
    self._is_rob_kong_window = True
    ...
```

**搶杠胡实现**：

| 组件 | 改动 |
|---|---|
| `_is_rob_kong_window` 标志 | 搶杠窗口开启时置 True |
| `get_available_actions()` | 搶杠窗口中只返回 `["win"]` 或 `["skip"]`，禁止碰/吃/杠 |
| `_resolve_claims()` 无人搶杠 | 调用 `_complete_extend_kong()`：记录杠钱、补摸牌、返回出牌阶段 |
| `_resolve_claims()` 有人搶杠 | 先将杠家 4 张副露回退为 3 张碰，再按普通荣和流程结算（搶杠者为赢家，杠家为放炮者） |
| `_complete_extend_kong()` | 新增方法：处理无搶杠时的杠后收尾逻辑 |

**新增测试**（`TestExtendPungKong` 5 个 + `TestRobTheKong` 2 个）：加杠出现在可用操作、加杠打开搶杠窗口、副露变 4 张、窗口限制只显示胡/过、全过后杠完成；搶杠胡结束游戏、搶杠后杠家副露回退为碰。

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/hand.py` | 平胡加 `ron` 条件；混幺九 `any()` → `all()`；七对 `is_winning_hand` 已启用 |
| `backend/game/game_state.py` | `MIN_HAN = 1`（可调）；`_is_rob_kong_window` 状态；`claim_kong()` 延伸碰路径；`get_available_actions()` 搶杠限制；`_resolve_claims()` 搶杠分支；`_complete_extend_kong()` 方法 |
| `backend/api/websocket.py` | `_pay()` 修正庄家赢时两倍付出 |
| `backend/tests/test_hand.py` | `TestSevenPairsWinningHand`（4）、`TestPingHuRonOnly`（已在 game_state 测试）、`TestHunYaoJiu` |
| `backend/tests/test_game_state.py` | `TestRonChipFormulaDealerWin`（5）、`TestMinimumFanRequirement`（4）、`TestExtendPungKong`（5）、`TestRobTheKong`（2） |

---

### 规则修正 #4：混幺九 番数 +2 → +3

**问题**：混幺九固定给 +2 番，港式标准为 +3 番。

**修复**（`backend/game/hand.py`）：将 `add('混幺九', ..., 2)` 改为 `add('混幺九', ..., 3)`。

**新增测试**（`TestHunYaoJiuFanValue`，1 个）：验证混幺九值为 3。

---

### 规则修正 #5：门清仅限荣和

**问题**：门清 +1 在自摸时也被授予；港式规则要求门清只适用于荣和（ron）。

**修复**（`backend/game/hand.py`）：在门清条件上增加 `and ron`：
```python
if not declared_melds and ron:
    add('门清', 'Concealed Hand', 1)
```
自摸门清手牌改为只获得 `自摸 +1`，不再叠加门清。

**新增测试**（`TestMenQingRonOnly`，2 个）：荣和时给门清、自摸时不给门清但给自摸。

---

### 规则修正 #8：嶺上開花（杠后摸牌胡）+1 番

**问题**：任何杠后补摸牌胡牌未额外计 +1 番。

**实现**：

1. `game_state.py`：新增 `self.lingshang_pending: bool = False` 标志位——杠后补摸牌时置 `True`，出牌时或 `_finalize_win` 消费后清除。

2. `hand.py`：`calculate_han` 新增 `ling_shang: bool = False` 参数，自摸且 `ling_shang=True` 时加 `嶺上開花 +1`：
```python
if ling_shang and not ron:
    add('嶺上開花', 'Kong Win (Lingshang)', 1)
```

**新增测试**（`TestLingShang`，2 个）：嶺上開花自摸 +1 番、荣和时不给嶺上開花。

---

### 规则修正 #9：本命花（座位花）+1 番/张

**问题**：收到与自己座位匹配的花牌/季牌无额外番数。

**座位花对应关系**：

| 座位 | 座位花 |
|---|---|
| 0（东） | FLOWER_1、SEASON_1 |
| 1（南） | FLOWER_2、SEASON_2 |
| 2（西） | FLOWER_3、SEASON_3 |
| 3（北） | FLOWER_4、SEASON_4 |

**实现**（`backend/game/hand.py`）：新增 `_SEAT_FLOWERS` 常量，`calculate_han` 新增 `player_seat: int = 0` 参数，每张匹配的本命花给 +1：
```python
seat_flower_set = _SEAT_FLOWERS.get(player_seat, frozenset())
for f in flowers:
    if f in seat_flower_set:
        add('本命花', 'Seat Flower', 1)
```

**新增测试**（`TestSeatFlower`，3 个）：本命花 +1、两张本命花 +2、非本命花不给分。

---

### 规则修正 #12：圈风追踪 + 自风碰/圈风碰 +1 番

**问题**：无圈风（场风）追踪，碰风牌无额外番数。

**规则**：
- **自风碰**：碰了本座位的风牌（如东家碰东风）→ +1 番
- **圈风碰**：碰了当前圈风牌 → +1 番
- 两者可叠加：东风圈中东家碰东风 = +2 番（自风碰 + 圈风碰）

**实现**：

| 文件 | 改动 |
|---|---|
| `room_manager.py` | `Room` 新增 `round_wind_idx: int = 0`、`dealer_advances: int = 0` |
| `websocket.py` | `_handle_game_over()` 每次换庄累计 `dealer_advances`，每满 4 次推进一轮圈风（东→南→西→北） |
| `game_state.py` | `__init__` 接受 `round_wind_idx`，传给 `calculate_han`，暴露在 `to_dict()` |
| `hand.py` | 新增 `_WIND_TILES` 常量、`round_wind_idx` 参数；检测自风碰/圈风碰并各给 +1 |

**新增测试**（`TestWindPungs`，4 个）：自风碰 +1、圈风碰 +1、东风圈东家碰东风两项均触发、不匹配时无加成。

---

### Bug 修复：大厅无法重新开局 + 状态/筹码显示异常

**发现时间**：游戏结束后用户返回大厅时

**现象**（三处独立问题）：

1. 房间状态显示原始字符串 `"ended"` 而非 `"已结束"`，无颜色样式
2. 筹码列显示 `"–"`（大厅拿不到筹码数据）
3. 已结束的房间无法重新开局——Join 按钮仅对 `"finished"` 禁用，`"ended"` 未处理；且大厅没有重开入口

**根本原因**：

| 问题 | 根因 |
|---|---|
| 状态显示异常 | `formatStatus`/`getStatusClass` 只映射了 `"finished"`，后端实际发 `"ended"` |
| 筹码为"-" | `Room.to_dict()` 未包含 `cumulative_scores` 和 `round_number` |
| 无重开入口 | 大厅无重开按钮；`"ended"` 房间需要引导用户回到游戏页使用"再来一局" |

**修复方案**：

**1. `backend/game/room_manager.py`**：`to_dict()` 新增 `cumulative_scores` 和 `round_number` 字段，让大厅可以读取当前筹码余额。

**2. `frontend/js/lobby.js`**：
- `formatStatus`：新增 `"ended"` → `"Finished 已结束"` 映射
- `getStatusClass`：新增 `"ended"` → `"status-finished"` 映射
- 房间行新增"筹码/Chips"列，显示当前玩家在该房间的余额
- `"ended"` 房间 Join 按钮改为 **"Rejoin 重回"**（灰色次级样式），玩家点击后进入游戏页，可在那里使用"再来一局"按钮

**3. `frontend/index.html`**：表头新增"筹码/Chips"列，`colspan` 调整为 5。

**4. `frontend/tests/lobby.test.js`**：更新 `formatStatus` 断言以匹配新双语格式，新增 `"ended"` 状态测试。

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/game/room_manager.py` | `to_dict()` 新增 `cumulative_scores`、`round_number` |
| `frontend/js/lobby.js` | 修复 `"ended"` 状态映射；添加筹码列；Rejoin 按钮 |
| `frontend/index.html` | 表头新增筹码列，colspan 5 |
| `frontend/tests/lobby.test.js` | 更新断言，新增 `"ended"` case |

---

### Bug 14：AI 玩家荣和后约 60 秒才显示结束弹窗

**发现时间**：正常游玩观察
**现象**：轮到 AI 玩家荣和（打出的牌被另一 AI 碰后再打出，第三 AI 叫胡），游戏结束弹窗要等约 60 秒才出现。

**根本原因**：`_handle_claim_window` 处理 AI 声索时，若某 AI 调用 `declare_win(i)` 成功，代码立即 `break` 退出 for 循环。但此时循环中尚未处理的其他 AI 仍留在 `_pending_claims` 中，导致 `_check_claim_window_closed()` 判断窗口未关闭（还有玩家未响应），游戏状态仍停在 `"claiming"` 阶段。

随后第 390 行执行：

```python
await asyncio.wait_for(_wait_for_claim_window(room_id), timeout=CLAIM_TIMEOUT)
```

`CLAIM_TIMEOUT = 30` 秒被完整等待，而如果连续出现两次这样的声索窗口，总延迟达到约 60 秒。

**修复方案**：在 AI 处理循环结束后，若检测到已存在胜利声索（`gs._best_claim["type"] == "win"`），立即强制跳过所有剩余 `_pending_claims`，使窗口即时关闭：

```python
if gs.phase == "claiming" and gs._best_claim is not None \
        and gs._best_claim.get("type") == "win":
    for _i in list(gs._pending_claims):
        if _i not in gs._skipped_claims:
            try:
                gs.skip_claim(_i)
            except ValueError:
                pass
```

**修改文件**：`backend/api/websocket.py` — `_handle_claim_window`（AI 处理循环与超时等待之间）

---

### 性能优化：非顺序切换玩家焦点时屏幕闪烁

**发现时间**：正常游玩（碰牌/吃牌后焦点跳转到非下家时）
**现象**：每次 `game_state` 消息到达时整个桌面闪烁，在碰/吃/杠等非顺序玩家切换时尤为明显。

**根本原因**（三处）：

1. **`active-turn` 类无 CSS 过渡**：`.player-area` 没有 `transition` 属性，金色边框/阴影在玩家间瞬间跳变。
2. **弃牌堆全量重建**：每次 `game_state` 都执行 `pileEl.innerHTML = ''` 后重建所有 SVG 牌元素，浏览器强制重新解码缓存图像。
3. **手牌全量重建**：即使手牌内容未变（如别人碰牌），也清空并重建所有 SVG 牌面元素。

**修复方案**：

1. **CSS 过渡**（`style.css`）：为 `.player-area` 添加 `transition: border-color 0.25s ease, box-shadow 0.25s ease`，使焦点切换平滑淡入淡出。
2. **弃牌堆差量更新**（`game.js` `renderCenterTable`）：
   - 相同 → 无操作
   - 末尾新增 1 张 → 仅 `appendChild`
   - 末尾移除 1 张（被声索）→ 仅 `.remove()` 最后一个元素
   - 其他（新局、窗口滑动）→ 全量重建
3. **手牌差量更新**（`game.html` `renderMyHand`）：以 `dataset.tilesKey` 缓存当前牌组 key，内容未变时跳过 `innerHTML` 重建，仅同步 `.selected` 状态。

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/css/style.css` | `.player-area` 新增 `transition` |
| `frontend/js/game.js` | `renderCenterTable` 改为增量更新 |
| `frontend/game.html` | `renderMyHand` 加 tilesKey 守卫；`renderOpponent` 手牌改增量加减 |

---

### 性能优化：前端渲染残余闪烁源全面消除

**发现时间**：系统性 code review
**现象**：即使手牌本身未变，每次 `game_state` 仍有多处不必要的 DOM 写入和 CSS 重计算。

**根本原因与修复**（逐项）：

| 问题 | 修复 |
|---|---|
| 对手背面牌：count 变化时 `innerHTML=''` 全量重建 | 改为逐个 `appendChild`/`.remove()`，不清空容器 |
| opponent label：每次无条件写 `innerHTML` | 用 `dataset.labelKey` 守卫，内容不变时跳过 |
| active-turn：每帧无条件 `classList.toggle` | 先 `contains()` 检查，只在真正变化时切换（3 处） |
| selectedTile 同步：每帧遍历所有手牌 DOM | 用 `dataset.selectedTile` 追踪，不变时跳过整个循环 |
| nameEl/scoreEl：每次无条件写 DOM | 比较新旧值，相同则跳过 |
| 弃牌堆滑动窗口（>12 张）：落入全量重建 | 识别"移除第一张+追加最后一张"场景，改增量操作 |
| wall count / phase 文本：每帧重复赋值 | 加 `textContent` 相等判断守卫 |
| `setStatus`：高频相同内容重复写 | 比较 msg + className，相同直接返回 |
| 声索弹窗/结束弹窗：`display:none→flex` 瞬间弹出 | 新增 `overlayFadeIn` 关键帧动画（opacity 0→1，0.15s/0.2s） |

**修改文件**：`frontend/game.html`、`frontend/js/game.js`、`frontend/css/style.css`

---

### 功能增强：吃牌多口选择

**发现时间**：用户反馈
**现象**：有多口可吃时（如手中有三四和六七，对家打出五），系统自动选择第一口（三四五），用户无法选择其他组合（四五六、五六七）。

**根本原因**：`autoSelectChow()` 仅返回第一口可行组合；`showClaimOverlay` 只生成单个"吃"按钮，无任何分支。

**修复方案**：

1. **新增 `getAllChows(discardedTile, hand)`**（`game.js`）：枚举三种顺子位置（倒数/中间/首位），返回所有可行的 2 元手牌数组列表（而非仅第一个）。`autoSelectChow` 重构为取其第一项，行为对外不变。

2. **`sendChow(handTiles)`**：新增可选参数；传入具体 2 张手牌时直接使用，否则降级至 `autoSelectChow` 自动选择。

3. **`showClaimOverlay` 多按钮渲染**（`game.js`）：
   - 仅一口可吃 → 保持原有单按钮"Chow 吃"
   - 多口可吃 → 每口生成独立按钮，标注三张牌的汉字序列（如「吃 三四五」「吃 四五六」「吃 五六七」），点击直接提交对应选择

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/js/game.js` | 新增 `getAllChows()`；重构 `autoSelectChow`；`sendChow(handTiles)` 支持参数；`showClaimOverlay` 多按钮分支 |
| `frontend/tests/game.test.js` | 新增 9 个 `getAllChows` 单元测试（null/荣誉牌/一口/两口/三口/跨花色/重复牌等） |
| `tests/integration/test_claim_window.py` | 新增 `TestClaimChowMultipleOptions`（6 个集成测试，手牌 3-4-6-7 + 弃牌 5，分别验证三口选择、拒绝无效牌、拒绝手中没有的牌） |

---

### Bug 修复：碰后点击杠导致所有操作失效

**发现时间**：用户报告（在能杠的情况下选择碰，底部操作栏仍显示杠按钮，点击后游戏卡死）

**现象**：手中有 3 张相同牌时，对家出同一张牌，声索窗口出现碰/杠选项。玩家选碰后，底部操作栏出现杠按钮（加杠/extend-pung 选项）。点击杠后所有按钮消失，游戏不可操作。

**根本原因（两处独立 bug，位于 `frontend/js/game.js` `sendKong()`）**：

**Bug A — `hideClaimOverlay()` 在非声索窗口时被调用**：

```javascript
// 修复前：末尾无条件调用 hideClaimOverlay()
function sendKong() {
  if (inClaimWindow) { ...; return; }
  if (selectedTile) {
    sendAction('kong', { tile: selectedTile });
  } else {
    // 自动检测...
  }
  hideClaimOverlay(); // ← BUG：不在声索窗口时也被调用
                       //       → pendingActions = [] → 按钮全消失
                       //       → 服务端返回 error 后无 action_required 恢复
}
```

**Bug B — 加杠牌检测遗漏"手中1张+碰副露"场景**：

```javascript
// 修复前：仅检测手中 4 张相同（暗杠），遗漏加杠（手中1张+碰副露3张）
const kongTile = Object.keys(counts).find(t => counts[t] >= 4);
```

玩家碰后手中只有 1 张该牌（已有碰副露），counts 不可能 >= 4，自动检测永远失败。

**修复方案**：

```javascript
function sendKong() {
  if (inClaimWindow) { ...; hideClaimOverlay(); return; }
  // 优先级：已选中的牌 > 加杠（手中1张+碰副露）> 暗杠（手中4张）
  let tileToKong = selectedTile || null;
  if (!tileToKong) {
    for (const meld of melds) {  // 先找加杠
      if (meld.length === 3 && meld[0] === meld[1] && meld[1] === meld[2]
          && hand.includes(meld[0])) { tileToKong = meld[0]; break; }
    }
  }
  if (!tileToKong) {  // 再找暗杠
    const counts = {}; hand.forEach(t => counts[t] = (counts[t] || 0) + 1);
    tileToKong = Object.keys(counts).find(t => counts[t] >= 4) || null;
  }
  if (tileToKong) {
    sendAction('kong', { tile: tileToKong });
    // 不调用 hideClaimOverlay()，由服务端 action_required 更新 UI
  } else {
    setStatus('Select the tile you want to Kong.', 'error');
  }
}
```

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/js/game.js` | `sendKong()` 修复两处 bug：hideClaimOverlay 只在声索窗口内调用；加杠检测优先于暗杠检测 |
| `tests/integration/test_claim_window.py` | 新增 `TestPungThenExtendPung`（5 个集成测试）：加杠可用性、四张副露形成、手牌减少、搶杠窗口、错误牌被拒绝 |

---

### Edge Case 测试专项（全面覆盖）

**背景**：系统性 code review 发现 20 个潜在 edge case，逐一分析当前行为后补充测试。

**新增测试（23 个，分布于 2 个文件）**：

**`backend/tests/test_hand.py`（15 个，4 个新测试类）**：

`TestCanChow` 新增（6 个）：
- `test_chow_kanchan_exact`：坎张，弃 5 手有 4-6 → 仅返回 [4,5,6] 一口
- `test_chow_tile_2_yields_two_options`：弃 2 手有 1-3-3-4 → 返回两口（1-2-3 和 2-3-4）
- `test_chow_tile_8_yields_two_options`：弃 8 手有 6-7-7-9 → 返回两口（6-7-8 和 7-8-9）
- `test_chow_1_correct_sequence`：边张低，仅 [1,2,3]，无越界（0-1-2 不合法）
- `test_chow_9_correct_sequence`：边张高，仅 [7,8,9]，无越界（8-9-10 不合法）

`TestSevenPairsFlushCombinations`（5 个）：
- 七对+清一色 同时给 +3+7；七对+混一色 +3+3；七对+字一色 +3+7
- 七对不触发碰碰胡（两者互斥）
- 七对+清一色荣和 total fan = 13（基本分+无花+门清+七对+清一色）

`TestLingShangPendingInGameState`（2 个）：
- 暗杠后 `lingshang_pending = True`
- 打牌后 `lingshang_pending = False`

`TestBonusTileChain`（3 个）：
- 单张花牌收取，1 张补牌消耗
- 两张花牌同时收取，恰好 2 张补牌消耗
- 补牌本身也是花牌时级联收取（FLOWER_1 → 补出 FLOWER_3 → 再补 BAMBOO_5）

**`tests/integration/test_claim_window.py`（8 个，`TestClaimChowEdgeTiles`）**：
- 边张低（弃 BAMBOO_1）：声索窗口含 chow；执行后副露 [1,2,3]
- 边张高（弃 BAMBOO_9）：副露 [7,8,9]
- 坎张（弃 5 手有 4-6）：副露 [4,5,6]；错误牌组被拒绝
- 弃 2 两口：分别选 [1,2,3] 和 [2,3,4] 各自生效
- 吃后手牌数精确校验（原始 5 张 → 消耗 2 → 剩余 3 张）

**Edge case 分析结论**（完整清单见下表）：

| Edge case | 结论 |
|---|---|
| 七对+清一色/混一色/字一色 | ✅ 代码正确，增加测试验证 |
| 七对不触发碰碰胡 | ✅ 互斥路径正确 |
| 嶺上開花荣和不给 | ✅ 已有测试，再次确认 |
| lingshang_pending 暗杠设 / 打牌清 | ✅ 新增测试验证 |
| 花牌级联替换 | ✅ while 循环正确处理，新增测试 |
| 花牌替换时牌墙为空 | ⚠️ 手牌少 1 张（warning 而非结束游戏），极罕见设计权衡 |
| 边张/坎张吃法 | ✅ 新增单元+集成测试全覆盖 |
| 弃2/弃8 两口选择 | ✅ 新增测试验证 |
| 吃后手牌数量精确 | ✅ 集成测试验证 |
| pung vs kong 同优先级 | ✅ 不可能同时发生（4 张牌限制），设计合理 |

**修改文件**：

| 文件 | 改动 |
|---|---|
| `backend/tests/test_hand.py` | 新增 4 个测试类，共 15 个 edge case 测试 |
| `tests/integration/test_claim_window.py` | 新增 `TestClaimChowEdgeTiles`，共 8 个集成测试 |

### 前端 Edge Case 测试补充

对上述 20 个 edge case 逐条分析前端可测性后，补充了 10 个纯函数单元测试（`frontend/tests/game.test.js`）：

**有前端等价逻辑并已补测（`getAllChows` + `autoSelectChow`）**：

| Edge case | 前端测试内容 |
|---|---|
| 边张低（弃1）| `getAllChows('BAMBOO_1', [2,3])` → 仅返回 `[[2,3]]`，越界组合 [0,1] 被过滤 |
| 边张高（弃9）| `getAllChows('BAMBOO_9', [7,8])` → 仅返回 `[[7,8]]`，越界组合 [10,11] 被过滤 |
| 坎张（弃5，手有4-6）| `getAllChows('BAMBOO_5', [4,6])` → 仅返回 `[[4,6]]` |
| 弃2两口 | `getAllChows('BAMBOO_2', [1,3,3,4])` → 返回 2 口：`[[1,3],[3,4]]` |
| 弃8两口 | `getAllChows('BAMBOO_8', [6,7,7,9])` → 返回 2 口：`[[6,7],[7,9]]` |
| `autoSelectChow` 多口取第一口 | 弃2手有[1,3,3,4]时返回 `[1,3]`（第一口），不取第二口 |
| `autoSelectChow` 边张低/高/坎张 | 各自返回唯一可用组合 |

**纯后端逻辑、前端无等价测试**：

| Edge case | 原因 |
|---|---|
| 七对+清一色/混一色/字一色 | `calculate_han` 在服务端执行，前端只渲染结果 |
| 花牌链（级联补牌）| 服务端 `_collect_bonus_tiles` 自动处理 |
| lingshang_pending 生命周期 | 服务端 `GameState` 内部状态，不暴露给前端 |
| 吃后手牌数量精确校验 | 服务端广播 `game_state` 后前端被动渲染 |

**修改文件**：`frontend/tests/game.test.js`（新增 2 个 describe 块，共 10 个测试）

---

## 测试体系

### 运行方式

**后端单元测试 + 覆盖率**
```bash
cd backend
pip install -r requirements-test.txt
pytest
# 输出：term-missing 覆盖率表 + htmlcov/ HTML 报告
```

**前端单元测试 + 覆盖率**
```bash
npm install
npm run test:coverage
# 输出：term 覆盖率表 + coverage/ HTML 报告
```

**集成测试**
```bash
cd tests/integration
pip install -r requirements.txt
pytest -v
```

### 覆盖率现状

| 模块 | 覆盖率 |
|---|---|
| `api/routes.py` | 100% |
| `game/room_manager.py` | 100% |
| `game/hand.py` | 97% |
| `game/tiles.py` | 96% |
| `game/ai_player.py` | 79% |
| `game/game_state.py` | 76% |
| 前端纯函数（branch） | 96.72% |

注：`api/websocket.py` 异步流程通过集成测试覆盖，未计入单元测试覆盖率。

### 集成测试分布

| 测试文件 | 测试数 | 覆盖范围 |
|---|---|---|
| `test_rest_api.py` | 14 | 全部 REST 端点（列出/创建/加入/开始房间） |
| `test_websocket.py` | 12 | WS 连接、游戏状态结构、手牌可见性、重开局（TestRestartGame） |
| `test_claim_window.py` | 29 | 碰/吃/杠/过/胡 完整声索窗口流程；多口吃牌三选一；边张/坎张 edge cases |
| `test_hand_order.py` | 7 | 服务端不排序验证 + Python 复现 JS 排序算法 |

### 测试总量

| 层级 | 测试数 |
|---|---|
| 后端单元测试 | 285 |
| 前端单元测试 | 95 |
| 集成测试 | 67 |
| **合计** | **447** |

`test_claim_window.py` 策略：通过 REST 开始游戏后直接操控 `room.game_state`，将局面固定到声索阶段（控制手牌、弃牌、已跳过玩家），再通过 WS 连接触发同步 `claim_window` 消息，验证声索结果。

---

## 功能增强：中文语音音效

### 技术方案

使用浏览器内置 **Web Speech API**（`speechSynthesis`），实现零音频文件、零后端改动、零外部依赖的中文语音播报。所有语音在运行时由系统 TTS 引擎实时合成，首次加载即可使用。

**浏览器支持**：Chrome / Edge（内置高质量普通话）、Safari（macOS/iOS 系统语音）、Firefox（取决于系统中文语音包）。无中文语音时静默降级。

### 新文件 `frontend/js/speech.js`

`SpeechEngine` 类：

```js
// 自动选择最佳中文语音（zh-CN > zh-TW/zh-HK > 任意 zh）
// 无中文语音时 #voice 为 null，所有 speak() 静默

speak(text, priority = false)   // priority=true 打断当前语音
speakTile(tileStr, priority = false)  // 查表并播报牌名
enable() / disable() / isEnabled()   // 开关（持久化至 localStorage）
```

**牌名映射表（`TILE_SPEECH`）**：

| 牌类 | 念法示例 |
|---|---|
| 条子 BAMBOO_1–9 | 一条 … 九条 |
| 饼子 CIRCLES_1–9 | 一饼 … 九饼 |
| 万字 CHARACTERS_1–9 | 一万 … 九万 |
| 风牌 | 东风 / 南风 / 西风 / 北风 |
| 字牌 | 中 / 发财 / 白板 |
| 花牌 | 梅花 / 兰花 / 菊花 / 竹子 |
| 季牌 | 春 / 夏 / 秋 / 冬 |

**语音参数**：`rate = 0.88`（偏慢，发音更清晰自然）；`pitch = 1.05`（略高，减少平板感）。

**语音优先级选择**（`_pickVoice`，从最佳到兜底）：
1. Google zh-CN（Chrome 内置 Neural TTS，音质最佳）
2. Google 任意 zh
3. Neural/Natural zh-CN（其他 Neural 声音）
4. 普通 zh-CN
5. zh-TW / zh-HK
6. 任意 zh 语音

**三模式播报引擎**（替换原有 priority 布尔值）：

| 模式 | 行为 | 用途 |
|---|---|---|
| `'skip'`（默认） | 正在播报则跳过 | 声索窗口牌名 |
| `'queue'` | 入队，当前结束后**立即**接着播 | 对手出牌牌名（改为 queue，避免被其他声音跳过）；对手碰/吃/杠 |
| `'immediate'` | 取消当前 + 清空队列 + 立即播 | 自己出牌牌名、自己碰/吃/杠/胡、胡了/流局 |

内部使用 `#active` 标志 + `#queue` 数组（最多存 1 项），`utt.onend` 回调自动消费队列，实现出牌牌名 → 对手操作的顺序衔接。

**典型时序**：
```
对手打 "三万"     → speakTile('skip')   → 播 "三万"
另一对手随即碰牌   → speak('queue')     → 入队
"三万" 播完        → onend 触发        → 立即接播 "碰"
```

### 触发时机

| 游戏事件 | 语音内容 | 模式 | 触发方式 |
|---|---|---|---|
| 任意玩家出牌（含 AI） | 牌名（如"三万"） | **`queue`** | `handleGameState` last_discard 变化（改为 queue，避免被跳过）|
| 声索窗口出现 | 可抢牌名 | `skip` | `handleClaimWindow` |
| 对手碰 | "碰" | **`queue`** / `immediate`* | `handleGameState` 副露增加且首张相同 |
| 对手吃 | "吃" | **`queue`** / `immediate`* | `handleGameState` 副露增加且首张不同 |
| 对手杠（含加杠） | "杠" | **`queue`** | `handleGameState` 副露增加且长≥4，或某副露3→4 |
| 我方出牌 | 牌名 | **`immediate`** | `sendDiscard` |
| 我方碰 | "碰！" | **`immediate`** | `sendPung` |
| 我方吃 | "吃！" | **`immediate`** | `sendChow` |
| 我方杠 | "杠！" | **`immediate`** | `sendKong` |
| 我方胡 | "胡！" | **`immediate`** | `sendWin` |
| 游戏结束-胡牌 | "胡了！" + 程序化音效 | **`immediate`** | `handleGameOver` + `playWinEffect()` |
| 游戏结束-流局 | "流局" | **`immediate`** | `handleGameOver` |

*对手碰/吃/杠模式取决于 `_myClaimSent` 标志：若本地玩家刚提交了声索但被他人抢先，用 `'immediate'` 取消挂起的本地声音；否则用 `'queue'`。

**双重播报防止**：我方操作由 `send*` 函数以 `'immediate'` 立即播报；`handleGameState` 的副露检测跳过 `myPlayerIdx`，不会重复播报自己的动作。

### 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/js/speech.js` | **新增**：SpeechEngine 类 + TILE_SPEECH 映射表 |
| `frontend/js/game.js` | `getSpeech()` 单例 getter；10 处 `speak()`/`speakTile()` 触发点；Topbar 静音按钮事件 |
| `frontend/game.html` | `<script src="js/speech.js">` 加在 game.js 之前；Topbar 🔊/🔇 切换按钮 |
| `frontend/css/style.css` | `#btn-speech` 及 `.muted` 样式 |

### 测试兼容性

Node.js / jsdom 无 `speechSynthesis`，`SpeechEngine` 构造函数和所有 `speak()` 调用对 `undefined` 做了防护，现有测试零改动、零回归。

### 后续音效 Bug 修复与增强

#### Bug 修复 1：吃/碰优先级声音乱序

**问题**：玩家点击"吃"后，若另一玩家碰牌优先，游戏先播"吃！"再播"碰"，顺序错误。

**根本原因**：`sendChow()` 用 `'immediate'` 播放"吃！"，随后 `handleGameState` 检测到另一玩家的碰副露，用 `'queue'` 排在"吃！"之后播"碰"。

**修复**：新增模块级 `_myClaimSent` 标志（`null | 'chow' | 'pung' | 'kong' | 'win'`）：
- `sendPung/sendChow/sendKong(claim)/sendWin` 在播报前设置标志
- `handleGameState` 副露检测：若 `_myClaimSent` 有值且另一玩家副露出现，用 `'immediate'` 取消挂起的"吃！"并播"碰"
- 循环结束后清除标志

#### Bug 修复 2：其他玩家出牌有时无声音

**问题**：其他玩家出牌后偶尔无牌名播报，尤其在本地玩家刚碰/吃之后。

**根本原因**：`speakTile(state.last_discard)` 使用默认 `'skip'` 模式，若此时"碰！"等声音仍在播放，牌名被静默跳过。

**修复**：改为 `speakTile(state.last_discard, 'queue')`，牌名排队等候当前语音结束后播出，不再丢失。

#### Bug 修复 3：摸牌不应播报牌名

**问题**：玩家自己摸到的牌也会播报牌名，体验不佳。

**修复**：删除 `handleActionRequired` 中的 `speakTile(msg.drawn_tile)` 调用。牌面自动高亮选中保留，仅取消语音播报。

#### 功能增强：胡牌程序化音效

`playWinEffect()` — 使用 Web Audio API 生成，零音频文件：

| 时间 | 内容 |
|---|---|
| 0s | 深沉锣声（55/110/220/440Hz 叠加正弦波，衰减约 3s） |
| 0.12–0.60s | 五声音阶上行：C5→E5→G5→A5→C6，每音加 2.76x 泛音（钟声质感） |
| 0.85s | 全音程和弦：低/中/高三层叠加 |
| 0.92–1.28s | 闪烁级联：11 个高频正弦脉冲上行再下行 |

由 `handleGameOver` 在有胡牌者时触发，与 TTS "胡了！" 同时播放。AudioContext 在 4.8s 后自动关闭。

**修改文件**：`frontend/js/game.js`（新增 `playWinEffect()`、`_myClaimSent` 标志、三处 bug 修复）

---

## 功能增强：移动端 UI（触屏支持 + 丝滑操作）

**开发方式**：使用 Claude Code 多 Agent 协作（css-agent + js-agent 并行）。

### CSS 改动（`style.css` + `game.html` + `index.html`）

| 改动 | 效果 |
|---|---|
| `html { touch-action: manipulation }` | 全局禁用双击缩放 |
| `viewport` 加 `maximum-scale=1.0, user-scalable=no` | 防止捏合缩放破坏布局 |
| `.my-hand .tile:hover` 移入 `@media (hover: hover)` | 消除手机端 hover 状态残留 |
| 新增 `@media (max-width: 600px)` 断点 | 专为手机定制样式 |
| `board-wrapper` grid 收缩：侧边 70px，上下行 90px | 四方牌桌在 375px 手机上完整显示 |
| `.my-hand` 横向滚动：`overflow-x: auto` + `-webkit-overflow-scrolling: touch` | 14 张手牌可左右滑动查看 |
| 手牌尺寸 32×46px（桌面 44×62px）| 手机屏幕容纳 14 张不溢出 |
| `#area-bottom overflow: visible` | 选中牌上浮不被裁切 |
| Action 按钮 `min-height: 44px` + `touch-action: manipulation` | 触控目标面积达标（Apple HIG 44pt 规范） |
| 声索弹窗 `min-width: 92vw`，声索牌 50×70px | 手机弹窗不溢出屏幕 |

### JS 改动（`game.js`）

| 改动 | 效果 |
|---|---|
| `makeTileEl()` 加 `touchAction: 'manipulation'` | 消除 iOS 300ms 点击延迟 |
| `makeClaimBtn()` 同上 | 声索按钮毫秒级响应 |
| `selectTile()` 末尾加 `scrollIntoView({ behavior:'smooth', inline:'center' })` | 选中的牌自动滚入视野 |
| `#my-hand` touchmove 监听器（`passive: false`）| 手牌区横滑时阻止页面纵向滚动穿透 |

### 新增测试（12 个，`frontend/tests/game.test.js`）

| 测试组 | 数量 | 覆盖内容 |
|---|---|---|
| `makeTileEl — touch interaction` | 5 | clickable 牌有 touch-action；face-down/非 clickable 无 |
| `makeClaimBtn — touch interaction` | 3 | 所有声索按钮有 touch-action；handler 注册正确 |
| `selectTile — scrollIntoView` | 4 | 支持时以正确参数调用；不支持时不报错；selected 类正确添加 |

**修改文件**：

| 文件 | 改动 |
|---|---|
| `frontend/css/style.css` | `touch-action`、`@media (hover:hover)` 重构、600px 断点（91 行新增） |
| `frontend/game.html` | viewport `user-scalable=no` |
| `frontend/index.html` | 同上 |
| `frontend/js/game.js` | 4 处 touch 交互改动；导出 `makeTileEl`、`makeClaimBtn`、`selectTile` |
| `frontend/tests/game.test.js` | 新增 12 个移动端单元测试 |

---

### 移动端竖屏布局专项迭代

经多轮截图反馈与调试，形成以下最终方案（仅针对竖屏手机，`@media (max-width: 600px)`）：

#### 核心布局重构：top/bottom 横跨全列

**问题**：原始 `grid-template-areas: ". top ." / ". bottom ."` 让对面玩家和我的手牌只占中间列（375px 手机上约 145px），极度拥挤。

**修复**：改为 `"top top top" / "bottom bottom bottom"`，对面玩家和我的手牌铺满全屏宽度（约 355px），显著改善。

```css
grid-template-areas:
  "top    top    top"      /* 对面玩家全宽 ~355px */
  "left   center right"   /* 75px | 1fr(215px) | 75px */
  "bottom bottom bottom"; /* 我的手牌全宽 ~355px */
grid-template-columns: 75px 1fr 75px;
grid-template-rows: min(80px, 14%) minmax(80px, 1fr) min(135px, 36%);
```

#### 弹窗高度修复（声索窗口按钮不显示）

- 新增 `@media (max-width: 900px)` 紧凑声索弹窗布局：h3 标题隐藏、牌面图与倒计时并排（节省约 60px）、按钮 38px、`max-height: 88vh + overflow-y: auto` 兜底
- 去除旧 600px 声索规则（迁移至 900px 块统一处理）

#### 玩家信息显示恢复

- **顶部玩家**：flex 行内显示名字（截断）+ 筹码，0.68rem
- **侧边玩家**（75px 宽）：`font-size: 0` 隐藏名字文字但保留 `dealer-badge`（庄字有自己的 `font-size: 0.72rem`），下方显示筹码 0.58rem
- **我的手牌区**：`#my-hand-label` 不变，显示名字 + 庄标 + 筹码

#### 大厅页（index.html）竖屏适配

| 改动 | 效果 |
|---|---|
| `rooms-table-wrap { overflow-x: auto }` | 房间表格 5 列可横向滑动访问 |
| `th/td` padding 缩小 | 列宽更紧凑 |
| Player ID UUID 加 `text-overflow: ellipsis` | 不再撑开页面布局 |
| `lobby-header h1` 2.4rem → 1.4rem | 标题不占过多空间 |

#### 迭代过程中修复的隐蔽 Bug

- **CSS 级联覆盖**：`game.html` 内联 `<style>` 在 HTML 中排在外部 `style.css` 之后，导致 style.css 里的媒体查询被内联样式覆盖。所有响应式规则必须写在 `game.html` 内联块中才能生效。
- **固定行高 vs 弹性行高**：`grid-template-rows: auto` 在副露出现时使底部行无限扩张，压垮中间行（left/center/right）。改为 `min(px, %)` 弹性值，同时解决矮屏（393px 高）和普通屏（667px 高）的兼容性。
- **`overflow: visible` vs `overflow-x: auto` 优先级**：`game.html` 用 ID 选择器（高优先级）设置 `#my-hand { overflow: visible }`，class 选择器的 `.my-hand { overflow-x: auto }` 无法覆盖。在 `@media` 块内用 `#my-hand { overflow-x: auto !important }` 解决。

**相关修改文件**（本轮迭代）：

| 文件 | 改动 |
|---|---|
| `frontend/game.html` | 竖屏 grid 重构；玩家标签显示恢复；声索弹窗布局调整 |
| `frontend/css/style.css` | `@media (max-width: 900px)` 声索弹窗紧凑布局；大厅页竖屏适配 |

---

## 功能增强：双击 / 双指快速出牌

**背景**：玩家出牌需要两步——先点击选中牌，再点击「打」按钮。双击牌可将两步合并为一步。

**实现**（`frontend/js/game.js` — `makeTileEl()`）：

针对桌面和移动端分别处理：

```javascript
// 桌面：dblclick 可靠
el.addEventListener('dblclick', () => {
  if (!pendingActions.includes('discard') || inClaimWindow) return;
  if (selectedTile !== tileStr) selectTile(tileStr, el);
  sendDiscard();
});

// 移动端：touch-action:manipulation 会抑制 dblclick，改用 touchend 时间差
el.addEventListener('touchend', (e) => {
  if (_dblTapTimer && _dblTapTile === tileStr) {
    clearTimeout(_dblTapTimer);
    e.preventDefault();   // 阻止合成 click（防止 toggle 取消选中）
    if (!pendingActions.includes('discard') || inClaimWindow) return;
    if (selectedTile !== tileStr) selectTile(tileStr, el);
    sendDiscard();
  } else {
    _dblTapTile  = tileStr;
    _dblTapTimer = setTimeout(() => { _dblTapTimer = _dblTapTile = null; }, 300);
  }
}, { passive: false });  // passive:false 才能 preventDefault
```

**为什么移动端不能直接用 `dblclick`**：`touch-action: manipulation` 告知浏览器接管双击手势（禁用双击缩放），导致 `dblclick` 事件可能被抑制。改用 `touchend` 手动计算两次触摸间隔（≤300ms = 双击），并用 `e.preventDefault()` 阻止第二次触摸产生的合成 `click`（否则 `selectTile` 的 toggle 逻辑会取消选中，导致 `sendDiscard` 时 `selectedTile = null`）。

**守卫条件**：
- `pendingActions.includes('discard')` — 仅在轮到自己出牌时生效
- `!inClaimWindow` — 声索弹窗期间不触发

**修改文件**：`frontend/js/game.js`（新增模块级 `_dblTapTimer` / `_dblTapTile`；`makeTileEl` clickable 分支加 `dblclick` + `touchend` 监听）

---

## 已知限制与后续扩展方向

| 项目 | 当前状态 | 可改进方向 |
|---|---|---|
| 状态持久化 | 纯内存，重启丢失 | 接入 Redis 或 SQLite |
| 玩家认证 | 无，player_id 自生成 | 加入 JWT/Session |
| 计分系统 | 番数驱动结算（unit=2^(n-1)，庄家双倍，杠钱即时，详见功能增强 5） | 天胡/地胡等特殊牌型；庄家轮换；番型加倍上限调整 |
| AI 强度 | 启发式贪心 | 蒙特卡洛或规则引擎 |
| 移动端适配 | 竖屏专项优化：top/bottom 全宽布局、声索弹窗紧凑、大厅表格横滑、玩家标签含庄标+筹码 | 横屏优化；E2E 浏览器测试（Playwright） |
| 测试覆盖 | 447 tests（后端 285 + 前端 95 + 集成 67），含声索窗口、多口吃牌、边张/坎张、碰后加杠、七对色番组合、花牌链、嶺上開花 flag、touch-action/scrollIntoView 移动端交互、手牌排序、加杠/搶杠胡、番数/圈风/本命花规则修正专项测试 | E2E 浏览器测试（Playwright）；lobby Rejoin 流程集成测试 |
| 多语言 | 界面为中英混合 | i18n 国际化 |
