# 麻将游戏 (Mahjong Game) — 项目文档

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
│       ├── test_tiles.py            # 52 tests
│       ├── test_hand.py             # 47 tests
│       ├── test_game_state.py       # 50 tests
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
│   └── tests/                       # 前端单元测试（Vitest）
│       ├── game.test.js             # 37 tests
│       └── lobby.test.js            # 19 tests
└── tests/
    └── integration/                 # 集成测试（pytest + httpx）
        ├── conftest.py              # TestClient fixtures
        ├── test_rest_api.py         # 14 tests
        ├── test_websocket.py        # 9 tests
        └── test_claim_window.py     # 15 tests（声索窗口完整流程）
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

牌面显示映射（`tileToDisplay()`）：

| 牌型 | 主字（`.tile-main`） | 副字（`.tile-sub`） | 颜色 |
|---|---|---|---|
| BAMBOO_1..9 | 一～九 | 条 | 墨绿 |
| CIRCLES_1..9 | 一～九 | 饼 | 深红 |
| CHARACTERS_1..9 | 一～九 | 萬 | 藏青 |
| EAST/SOUTH/WEST/NORTH | 東南西北 | — | 深色 |
| RED/GREEN/WHITE | 中/發/白 | — | 各异 |
| FLOWER_1..4 | 梅蘭菊竹 | — | 紫色 |
| SEASON_1..4 | 春夏秋冬 | — | 橙色 |

**牌面视觉风格**：
- 象牙骨色渐变背景 + 3D 浮雕边框（亮色上/左 + 暗色下/右）模拟实体麻将牌质感
- 背面牌采用 45° 条纹图案
- 字体：Noto Serif SC（Google Fonts）提供传统宋/楷体汉字渲染
- 手牌 44×62px / 弃牌 26×36px / 声索弹窗 56×78px，各区域独立缩放

**WebSocket 断线重连**：2 秒后自动重连。

---

## 代码规模统计

| 文件 | 行数 | 说明 |
|---|---|---|
| `game/game_state.py` | 805 | 核心状态机 |
| `game/ai_player.py` | 371 | AI 逻辑 |
| `game/hand.py` | 313 | 胡牌算法 |
| `game/tiles.py` | 201 | 牌型定义 |
| `game/room_manager.py` | 218 | 房间管理 |
| `api/websocket.py` | 664 | WebSocket 处理 |
| `api/routes.py` | 102 | REST 接口 |
| `main.py` | 54 | 应用入口 |
| `frontend/js/game.js` | 880 | 游戏客户端 |
| `frontend/js/lobby.js` | 177 | 大厅客户端 |
| `frontend/css/style.css` | 760 | 样式表 |
| **业务代码合计** | **~4,470** | |
| `backend/tests/` | ~900 | 后端单元测试（233 tests） |
| `frontend/tests/` | ~420 | 前端单元测试（64 tests） |
| `tests/integration/` | ~1,100 | 集成测试（45 tests） |
| **测试代码合计** | **~2,420** | |

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
| `test_websocket.py` | 9 | WS 连接、游戏状态结构、手牌可见性 |
| `test_claim_window.py` | 15 | 碰/吃/杠/过/胡 完整声索窗口流程 |
| `test_hand_order.py` | 7 | 服务端不排序验证 + Python 复现 JS 排序算法 |

`test_claim_window.py` 策略：通过 REST 开始游戏后直接操控 `room.game_state`，将局面固定到声索阶段（控制手牌、弃牌、已跳过玩家），再通过 WS 连接触发同步 `claim_window` 消息，验证声索结果。

---

## 已知限制与后续扩展方向

| 项目 | 当前状态 | 可改进方向 |
|---|---|---|
| 状态持久化 | 纯内存，重启丢失 | 接入 Redis 或 SQLite |
| 玩家认证 | 无，player_id 自生成 | 加入 JWT/Session |
| 计分系统 | 简化版（基础分 + 副加分） | 完整番种计算 |
| AI 强度 | 启发式贪心 | 蒙特卡洛或规则引擎 |
| 移动端适配 | 桌面优先（1024px+） | 触屏手势支持 |
| 测试覆盖 | 349 tests，含声索窗口 + 手牌排序 + 副露胡牌 + 重开局集成测试 | E2E 浏览器测试（Playwright） |
| 多语言 | 界面为中英混合 | i18n 国际化 |
