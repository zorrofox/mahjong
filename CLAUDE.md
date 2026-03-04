# 麻将游戏 (Mahjong Game) — 项目文档

> **语言约定**：请始终用中文回复用户。

## 项目概述

基于浏览器的多人麻将游戏，支持 1–4 名玩家共享一个房间，空位由 AI 自动填补。采用标准中国香港麻将规则，Python FastAPI 后端 + 原生 HTML/JS 前端，通过 WebSocket 实现实时通信，部署于 Google Cloud Run + IAP。

---

## 快速启动

**本地开发**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
打开浏览器访问 `http://localhost:8000`。

**生产环境（Google Cloud Run）**

服务已部署至：`https://YOUR_CLOUD_RUN_URL`（需要 Google 身份认证）

访问受 IAP（Identity-Aware Proxy）保护的公网入口：`https://YOUR_APP_DOMAIN`

---

## 项目结构

```
majiang/
├── CLAUDE.md                        # 本文档
├── Dockerfile                       # Cloud Run 容器镜像构建
├── .dockerignore                    # Docker 构建排除规则
├── .gcloudignore                    # gcloud 部署排除规则
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
│       ├── test_tiles.py
│       ├── test_hand.py
│       ├── test_game_state.py
│       ├── test_ai_player.py
│       ├── test_room_manager.py
│       └── test_routes.py
├── frontend/
│   ├── index.html                   # 大厅页：房间列表、创建/加入
│   ├── game.html                    # 游戏页：四方牌桌、手牌、操作按钮
│   ├── css/
│   │   └── style.css                # 绿毡主题样式、响应式布局
│   ├── js/
│   │   ├── lobby.js                 # 大厅逻辑：轮询房间列表
│   │   ├── game.js                  # 游戏逻辑：WebSocket 客户端、渲染
│   │   └── speech.js                # 中文语音音效（Web Speech API）
│   └── tiles/                       # Cangjie6 港式麻将 SVG 牌面（42 张）
└── tests/
    └── integration/                 # 集成测试（pytest + httpx）
        ├── conftest.py
        ├── test_rest_api.py
        ├── test_websocket.py
        ├── test_claim_window.py
        └── test_hand_order.py
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

## 核心规则实现

### 牌型（`tiles.py`）

144 张标准麻将：万子/条子/筒子各 9 种 × 4 张（108 张）、风牌东南西北各 4 张（16 张）、字牌中发白各 4 张（12 张）、花牌/季牌各 1 张（8 张）。牌以字符串表示，如 `"BAMBOO_5"`、`"EAST"`、`"RED"`、`"FLOWER_1"`。

### 胡牌判断（`hand.py`）

`is_winning_hand_given_melds(concealed_tiles, n_declared_melds)` 使用递归回溯：枚举对子候选，移除后尝试从最小牌起剥离刻子或顺子，恰好剥完 `(4 - n_melds)` 组即为胡牌。副露牌保持锁定，不参与重组。额外支持七对子（7 个不同对子）。

### 游戏状态机（`game_state.py`）

```
drawing → discarding → claiming → (下一轮 drawing)
                                ↓
                             ended（有人胡牌或牌墙摸空）
```

关键设计：
- **声索优先级**：胡 > 碰/杠 > 吃；同优先级取距出牌者座位最近者（`_seat_distance`）
- **花牌自动收取**：摸到花牌立即从牌墙后端补牌（`_collect_bonus_tiles`，支持级联）
- **杠后补牌**：从牌墙后端补一张；`last_drawn_tile` 在 `_collect_bonus_tiles` 之后用 `hand[-1]` 更新
- **人类玩家摸牌**：drawing 阶段由服务端自动完成，不暴露 draw 消息给客户端
- **嶺上開花**：杠后补牌时设 `lingshang_pending=True`，`_finalize_win` 消费后清除，出牌时清除
- **搶杠胡**：加杠时开搶杠声索窗口；声索窗口中只允许胡/过；无人搶杠才完成杠

### AI 逻辑（`ai_player.py`）

- **出牌**：为每张牌打分（已成副 +30、刻子 +25、对子 +15、相邻 +4、孤张 -5），优先打分最低的牌
- **声索决策**：永远声索胡牌；碰/杠/吃在模拟后若进度分提升则声索
- **副露胡牌检查**：使用 `is_winning_hand_given_melds(playable, n_melds)`，与服务端逻辑一致

### 房间管理（`room_manager.py`）

每房间最多 4 名人类玩家；`join_room()` 若目标房间已满自动创建新房间（返回 `was_redirected=True`）；`start_game()` 用 `ai_player_1..3` 填满空位并发牌。

---

## 番数与筹码结算

### 番型（港式规则，16 种）

| 番型 | 番数 | 条件 |
|---|---|---|
| 基本分 | +1 | 始终 |
| 自摸 | +1 | 自摸 |
| 无花 | +1 | 无花/季牌 |
| 门清 | +1 | 无副露**且荣和** |
| 平胡 | +1 | 全顺子 + 对子 2–8 + 门清**且荣和** |
| 断幺 | +1 | 全部牌为 2–8，无幺九风字 |
| 嶺上開花 | +1 | 杠后补摸牌自摸 |
| 本命花 | +1/张 | 与座位匹配的花/季牌（seat 0=梅春，1=兰夏，2=菊秋，3=竹冬） |
| 自风碰 | +1 | 碰本座位风牌 |
| 圈风碰 | +1 | 碰当前圈风牌（可与自风碰叠加） |
| 混幺九 | +3 | 每组及对子内**每张**均为幺九或风字（`all()`，非 `any()`） |
| 七对 | +3 | 七个不同对子 |
| 碰碰胡 | +3 | 四副全刻子 |
| 混一色 | +3 | 纯一花色数牌 + 风字 |
| 小三元 | +5 | 两副字牌刻子 + 对子为第三种字牌 |
| 小四喜 | +6 | 三副风牌刻子 + 对子为第四种风牌 |
| 清一色 | +7 | 纯一花色，无风字 |
| 字一色 | +7 | 全风牌或字牌 |
| 大三元 | +8 | 三副字牌（中/發/白）刻子 |
| 大四喜 | +13 | 四副风牌（东南西北）刻子 |

### 筹码结算公式

```
unit = min(CHIP_CAP, 2^(番数-1))
  1番→1u  2番→2u  3番→4u  4番→8u  5番→16u  6番→32u  7番+→64u

自摸（闲家赢）：庄付 2u + 两位闲各付 1u → 赢家收 +4u
自摸（庄家赢）：三位闲各付 2u → 赢家收 +6u
荣和：放炮者独付全额（其余玩家不付）
  闲家赢 → 放炮者付 4u
  庄家赢 → 放炮者付 6u（无论放炮者是庄还是闲）
杠钱：每次杠各家付 1 筹码（固定，不受番数影响）
```

### 重要配置常量

| 常量 | 位置 | 默认值 | 说明 |
|---|---|---|---|
| `MIN_HAN` | `game_state.py` | 1 | 最低起胡番数（3 = 港式赛事严格规则） |
| `INITIAL_CHIPS` | `room_manager.py` | 1000 | 初始筹码 |
| `CHIP_CAP` | `websocket.py` | 64 | 单局最大支付单位（7 番封顶） |
| `CLAIM_TIMEOUT` | `websocket.py` | 30.0 | 声索窗口超时秒数 |
| `AI_TAKEOVER_GRACE` | `websocket.py` | 20.0 | 断线后 AI 接管宽限期（秒） |

---

## API 接口

### REST（`/api/...`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/rooms` | 获取所有房间列表 |
| POST | `/api/rooms` | 创建新房间（可选 `name` 字段） |
| POST | `/api/rooms/{id}/join` | 加入房间，body: `{"player_id": "..."}` |
| POST | `/api/rooms/{id}/start` | 开始游戏（补 AI、发牌） |

### WebSocket（`/ws/{room_id}/{player_id}`）

**客户端 → 服务器：**

| 消息类型 | 说明 |
|---|---|
| `discard` + `tile` | 出牌 |
| `pung` | 碰 |
| `chow` + `tiles` | 吃（指定 2 张手牌） |
| `kong` + `tile` | 杠（暗杠/加杠/声索杠） |
| `win` | 声明胡牌 |
| `skip` | 过（放弃声索） |
| `restart_game` | 重开局 |

**服务器 → 客户端：**

| 消息类型 | 关键字段 |
|---|---|
| `game_state` | `players`、`discards`、`phase`、`cumulative_scores`、`dealer_idx`、`round_wind_idx` |
| `action_required` | `actions`、`drawn_tile` |
| `claim_window` | `tile`、`actions`、`timeout` |
| `game_over` | `winner_id`、`win_ron`、`han_breakdown`、`han_total`、`chip_changes`、`cumulative_scores`、`dealer_idx`、`next_dealer_idx` |

---

## 前端架构要点

### 牌面渲染

- SVG 路径：`frontend/tiles/`（42 张 Cangjie6 斜视 3D 港式麻将，CC BY-SA 4.0）
- `TILE_SVG_MAP` → `makeTileEl()` 生成 `<img class="tile-img">` 元素；加载失败时回退文字
- 背面牌：纯 CSS 蓝色 45° 斜条纹，无图片

### 重要覆盖关系

`game.html` 内联脚本通过 `window.renderOpponent` 和 `window.renderMyHand` 覆盖 `game.js` 中的同名函数，以使用页面预建 DOM 元素。**修改渲染逻辑时必须同时检查两处。**

### 缓存破坏

JS/CSS 文件通过 `?v=YYYYMMDD` 版本号强制刷新浏览器缓存。前端有改动时递增版本号。

### 差量更新优化

手牌/弃牌/副露/对手背面牌均采用差量 DOM 更新，仅内容变化时重建，避免全量 `innerHTML` 导致的闪烁。关键缓存 key：`dataset.tilesKey`、`dataset.meldsKey`、`dataset.labelKey`。

### 音效（`speech.js`）

- Web Speech API 实现中文 TTS（零音频文件），Web Audio API 实现程序化音效
- `SpeechEngine` 支持 `skip`/`queue`/`immediate` 三种优先级模式
- `_sharedAudioCtx`：共享单例 `AudioContext`，首次用户点击时解锁（解决 iOS 静默问题）
- `handleActionRequired` 等待 TTS 播完后再显示操作按钮，使音效与 UI 时序同步

### 移动端

- `@media (max-width: 600px)` 竖屏布局：top/bottom 区域横跨全列，侧边 75px
- 手牌区横向滚动（`overflow-x: auto`），选中牌自动滚入视野（`scrollIntoView`）
- `touch-action: manipulation` 消除 iOS 300ms 点击延迟
- 双击/双指快速出牌：桌面用 `dblclick`，移动端用 `touchend` 时间差（≤300ms）
- 结束弹窗：移动端改为 Bottom Sheet（贴底，`max-height: 55vh`），上半屏显示翻牌

---

## 庄家与圈风规则

- **连庄**：庄家赢牌（自摸或荣和）→ 下局仍为庄
- **换庄**：闲家赢牌或流局 → 下局顺时针 +1 换庄
- **圈风推进**：每 4 次换庄推进一次圈风（东→南→西→北）
- `game_over` 同时携带 `dealer_idx`（当局）和 `next_dealer_idx`（下局）
- 下一局庄家有权触发"再来一局"；庄家为 AI 时任何人可触发

---

## 断线与重连

- 断线后启动 `AI_TAKEOVER_GRACE=20s` 宽限期计时器，期内重连可无缝恢复，`is_ai` 不被置位
- 超时后 AI 正式接管，之后重连仍会恢复为人类控制（`is_ai=False`）
- 重连已结束房间：服务端发 `game_state`（含 `cumulative_scores`）+ `game_over(is_reconnect=True)`，前端显示结算弹窗，允许所有在线玩家重开
- `restart_game` 时，未连线的人类玩家自动标为 AI，保证游戏不因等待而卡死
- `chip_changes` 由后端计算并持久化在 `room.last_chip_changes`，重连时直接取值

---

## 测试体系

### 运行方式

```bash
# 后端单元测试 + 覆盖率
cd backend
pip install -r requirements-test.txt
pytest

# 前端单元测试 + 覆盖率
npm install
npm run test:coverage

# 集成测试
cd tests/integration
pip install -r requirements.txt
pytest -v
```

### 覆盖率

| 模块 | 覆盖率 |
|---|---|
| `api/routes.py` | 100% |
| `game/room_manager.py` | 100% |
| `game/hand.py` | 97% |
| `game/tiles.py` | 96% |
| `game/ai_player.py` | 79% |
| `game/game_state.py` | 76% |
| 前端纯函数（branch） | 96.72% |

### 测试分布

| 层级 | 测试数 | 覆盖范围 |
|---|---|---|
| 后端单元测试 | 360 | tiles/hand/game_state/ai_player/room_manager/routes/dalian_hand/dalian_settlement |
| 前端单元测试 | 111 | game.js 纯函数（排序、番数渲染、touch 交互等） |
| 集成测试 | 79 | REST 端点、WS 流程、声索窗口、重开局、Rejoin |
| **合计** | **550** | |

---

## 生产部署（Google Cloud Run + IAP）

```bash
IMAGE="us-central1-docker.pkg.dev/YOUR_PROJECT/mahjong-repo/mahjong:latest"
docker build -t ${IMAGE} . && docker push ${IMAGE}

gcloud run deploy mahjong \
  --image=${IMAGE} --platform=managed --region=us-central1 \
  --no-allow-unauthenticated \
  --ingress=internal-and-cloud-load-balancing \
  --port=8080 --memory=512Mi --cpu=1 \
  --min-instances=0 --max-instances=10
```

**架构**：浏览器 → HTTPS LB + IAP（Google OAuth）→ Serverless NEG → Cloud Run（FastAPI + Uvicorn）

**注意事项**：
- Cloud Run 无状态，游戏状态纯内存，实例重启后丢失
- 多实例时同房间玩家须路由到同一实例（当前无粘性路由，建议 `min-instances=1`）
- WebSocket 需要 HTTP/1.1，通过 LB 时走 `wss://`
- `API_BASE`/`WS_BASE` 动态判断：本地用 `http://localhost:PORT`，生产用相对路径和 `wss://`
- IAP 需要专属服务代理账号并授予 Cloud Run Invoker 权限

---

## 重要 Bug 修复记录

| # | 问题摘要 | 修复位置 | 关键教训 |
|---|---|---|---|
| 1 | `player.hand` 序列化为对象而非数组 | `game.js` `getHandTiles()`/`getHandCount()` | 前后端字段格式须对齐 |
| 2 | `room_update` 消息未处理致控制台警告 | `game.js` switch case | 添加静默 break |
| 3 | 人类玩家 drawing 阶段卡死 | `websocket.py` `_run_ai_turn` | 摸牌由服务端自动完成，不暴露给客户端 |
| 4 | AI 出牌后人类等待约 19 秒 | `websocket.py` `_handle_claim_window` | 对只有 skip 可选的玩家立即自动跳过 |
| 5 | 已自动跳过玩家仍收到 `actions=[]` 消息 | `websocket.py` `_send_claim_window` | 操作列表为空则不发送 |
| 6 | 荣和时手牌重复添加、得分未计算 | `game_state.py` `declare_win`/`_resolve_claims` | 验证用副本；实际修改在 `_resolve_claims` 唯一执行 |
| 7 | `autoSelectChow` 标签解析错误 | `game.js:615` | `label.slice(1)` 非 `slice(0,-1)` |
| 8 | 有副露时无法胡牌 | `game_state.py` `get_available_actions`/`declare_win` | 使用 `is_winning_hand_given_melds(hand, n_melds)` |
| 9 | 重连后座位变全 AI 操作 | `websocket.py` 重连处理 | 重连时必须重置 `player.is_ai=False` |
| 10 | 手牌排序被 `game.html` 内联函数覆盖 | `game.html` `window.renderMyHand` | 内联覆盖函数优先级高于 `game.js`，修改须同步 |
| 11 | 碰后点击杠导致操作失效 | `game.js` `sendKong()` | 验证 `selectedTile` 是否真的可杠；仅在声索窗口内调 `hideClaimOverlay` |
| 12 | 声索窗口点"过"后游戏卡死 | `websocket.py` `_handle_claim_window` | 引入 `_claim_window_active` 防止双重 `_run_ai_turn` 竞态 |
| 13 | AI 荣和后弹窗延迟约 60 秒 | `websocket.py` `_handle_claim_window` | AI 胡牌后立即强制跳过其余 pending 玩家 |
| 14 | 多人场景人类荣和后游戏卡死 | `websocket.py` win 处理器 + `_handle_game_over` | 人类 win 后同样需要 force-skip；`_handle_game_over` 加幂等守卫（检查 `room.status=="ended"`） |
| 15 | 副露牌被混入自由牌池导致胡牌假阳性 | `hand.py` 新增 `is_winning_hand_given_melds` | 副露锁定，不参与重组；旧接口 `is_winning_hand(hand+meld_tiles)` 存在根本性缺陷 |
| 16 | 声索杠补牌为花牌时 `last_drawn_tile` 错误，Discard 失效 | `game_state.py` `_resolve_claims` | `_collect_bonus_tiles` 后用 `hand[-1]` 更新 `last_drawn_tile`（暗杠/加杠路径已同步修复） |
| 17 | 加杠后搶杠声索窗口未启动，窗口永久卡死 | `websocket.py` kong handler | 加杠后必须触发 `_handle_claim_window` |
| 18 | 跳过暗杠后下一轮杠发送错误牌 | `game.js` `sendKong()` | 使用 `selectedTile` 前须验证手牌满足杠条件 |
| 19 | 重连时本局筹码变化全为 0 | `websocket.py` + `room_manager.py` | `chip_changes` 由后端计算并持久化在 `room.last_chip_changes`，不依赖前端差值 |
| 20 | iOS 移动端程序化音效完全无声 | `game.js` `_getAC()` | 共享单例 `AudioContext`，首次用户点击时解锁（iOS 要求在手势同步回调中创建 AudioContext） |
| 21 | 本命花多张时结算弹窗出现重复行 | `hand.py` `calculate_han` | 先统计匹配数量再合并为一条 `add('本命花', ..., count)`，其余番型经逐一验证均不存在重复调用 |
| 22 | 新局开始时对手手牌区残留上局翻牌 | `game.html` `renderOpponent` else 分支 | reveal→normal 切换时，需先检查 `dataset.tilesKey` 是否含 `\|reveal\|`，若是则清空容器再走差量逻辑；`.tile-back` 计数不会清除正面 SVG 图片 |
| 23 | AI `should_declare_win` 有副露时误判（假阳性/假阴性） | `ai_player.py` `should_declare_win` | 改用 `is_winning_hand_given_melds(playable, len(melds))` 替代旧版 `is_winning_hand(hand + meld_tiles)`；副露牌不能混入自由牌池 |
| 24 | 同优先级声索（碰 vs 碰 / 杠 vs 杠）后者覆盖先者 | `game_state.py` `claim_pung`/`claim_kong` | 同优先级改为取座位距离最近者（`_seat_distance`）；修复前用 `>=` 导致后来者无条件覆盖 |
| 25 | 声索验证传 `player.hand` 而非 `hand_without_bonus()` | `game_state.py` `claim_pung`/`claim_kong`/`claim_chow` | 花牌滞留手中时验证结果与 `get_available_actions` 不一致；统一改用 `hand_without_bonus()` |
| 26 | 庄家荣和筹码公式错误（应收 6u 实收 3u） | `websocket.py` `_pay()` | 庄家赢时 `winner_idx == dealer_idx`，所有 payer 均为闲家，应一律返回 `2*unit`；原代码因 payer_idx 判断路径错误只返回 `1*unit` |
| 27 | 七对子 + 本命花不叠加（本命花番数丢失） | `hand.py` `calculate_han` | 七对子分支提前 `return`，跳过了本命花与嶺上開花计算；修复：在 `return` 前插入本命花/嶺上開花逻辑，本命花与手牌结构无关，所有胡型均应计入 |

---

## 已知限制

| 项目 | 当前状态 | 可改进方向 |
|---|---|---|
| 状态持久化 | 纯内存，重启丢失 | Redis / SQLite |
| 玩家认证 | 无，player_id 自生成 | JWT / Session |
| AI 强度 | 启发式贪心 | 蒙特卡洛或规则引擎 |
| 多实例路由 | 同房间玩家须路由到同实例 | WebSocket 粘性路由 / 共享状态 |
| 测试覆盖 | 504 tests | E2E 浏览器测试（Playwright） |
| 横屏适配 | 未专项优化 | 横屏布局调整 |
