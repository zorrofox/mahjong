# 麻将游戏 (Mahjong Game) — 项目文档

> **语言约定**：请始终用中文回复用户。

## 项目概述

基于浏览器的多人麻将游戏，支持 1–4 名玩家共享一个房间，空位由 AI 自动填补。**同时支持两种规则集**：
- **港式麻将**（`ruleset="hk"`）：144 张（含花/季牌），标准香港规则
- **大连穷胡**（`ruleset="dalian"`）：136 张（无花/季牌），含三色全/幺九/至少一刻/禁止门清/宝牌机制

Python FastAPI 后端 + 原生 HTML/JS 前端，通过 WebSocket 实现实时通信，部署于 Google Cloud Run + IAP。

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
│       ├── test_routes.py
│       ├── test_dalian_hand.py      # 大连穷胡手牌规则测试（含宝牌/听牌/冲摸宝）
│       ├── test_dalian_settlement.py # 大连穷胡结算逻辑测试
│       └── test_dalian_game_state.py # 大连穷胡状态机测试（荒庄/禁碰/宝牌/不换听）
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

`build_deck(ruleset="hk")` 按规则集生成牌组：
- **港式**（`"hk"`）：144 张（含花牌/季牌各 4 张）
- **大连**（`"dalian"`）：136 张（无花/季牌）

牌以字符串表示，如 `"BAMBOO_5"`、`"EAST"`、`"RED"`、`"FLOWER_1"`。

### 胡牌判断（`hand.py`）

**港式函数：**
- `is_winning_hand_given_melds(concealed_tiles, n_declared_melds)`：递归回溯，支持七对子

**大连穷胡函数：**
- `is_winning_hand_dalian(concealed, n_melds, declared_melds, bao_tile=None)`：验证六个条件（禁止门清/三色全/幺九/至少一刻/禁手把一/结构），支持宝牌野牌替换
- `is_tenpai_dalian(concealed, n_melds, declared_melds, bao_tile=None)`：遍历 34 种候选张，返回所有等待张列表
- `decompose_winning_hand_dalian(concealed)`：三元牌禁刻子的手牌分解
- `calculate_han_dalian(...)`:  基础/自摸/夹胡/庄家/杠上开花(+2)/抢杠胡(+2)/冲宝(+2)/摸宝(+1)

### 游戏状态机（`game_state.py`）

```
drawing → discarding → claiming → (下一轮 drawing)
                                ↓
                             ended（有人胡牌或牌墙摸空）
```

关键设计：
- **声索优先级**：胡 > 碰/杠 > 吃；同优先级取距出牌者座位最近者（`_seat_distance`）
- **花牌自动收取**（HK）：摸到花牌立即从牌墙后端补牌（`_collect_bonus_tiles`，支持级联）
- **杠后补牌**：从牌墙后端补一张；`last_drawn_tile` 在 `_collect_bonus_tiles` 之后用 `hand[-1]` 更新
- **嶺上開花**：杠后补牌时设 `lingshang_pending=True`，`_finalize_win` 消费后清除
- **搶杠胡**：加杠时开搶杠声索窗口；仅允许胡/过；无人搶杠才完成杠
- **大连荒庄**：牌墙 ≤14 张（7 墩）时游戏结束，庄不换
- **大连三元牌禁碰**：`claim_pung` 对 RED/GREEN/WHITE 直接返回 False
- **大连宝牌**：`check_and_trigger_bao()` 在每次出牌后检测首次结构性听牌（`bao_tile=None`），触发骰子确定宝牌；`bao_tile` 字段在整局游戏中持久有效
- **大连宝牌野牌限制**：`_effective_bao(player_idx)` 辅助方法——仅对 `tenpai_players` 中的玩家返回 `bao_tile`，其他玩家返回 `None`。所有胡牌判断（`declare_win`/`get_available_actions`/`_finalize_win`/`_resolve_claims`/AI 决策）均通过此方法传递，确保「听牌后」的规则要求
- **大连换宝**：`_count_bao_revealed()` 统计弃牌堆 + 非暗杠副露中的宝牌总数；`check_and_maybe_reroll_bao()` 在每次出牌/碰/吃/杠完成后调用，达到 3 张时重摇并广播
- **大连听牌约束**：`discard_tile()` 对大连听牌玩家验证出牌后仍满足结构性 `is_tenpai_dalian`（`bao_tile=None`，不换听）；设有安全阀：若所有牌均无法合法出（可能因误加入 tenpai_players），自动从 tenpai_players 移除，防止死锁
- **大连听牌自动处理**：websocket 层对 tenpai_players 中的人类玩家，摸牌后自动判断（胡牌张→自动胡，其他张→自动打回）

### AI 逻辑（`ai_player.py`）

**港式策略：**
- `choose_discard(hand, melds, ruleset="hk")`：基于连通性评分，孤张优先丢弃
- `should_declare_win(hand, melds, ruleset="hk", bao_tile=None)`：按规则集调用对应胡牌检测

**大连专属策略（`_discard_score_dalian`）：**
- 宝牌保护：手中宝牌评分 +80，不轻易丢弃
- 三色全保护：副露未覆盖的稀缺花色最后 1 张 +80、≤3 张 +30
- 幺九保护：唯一字牌且无幺九 +25；最后幺九牌 +30
- 三元牌策略：第 3 张龙牌 -200 立即丢弃
- 刻子保护：对子/刻子候选额外加分

### 房间管理（`room_manager.py`）

`Room` 含 `ruleset` 字段（`"hk"` / `"dalian"`）；`create_room(ruleset=)` 接受规则集；`start_game()` 将 ruleset 传给 `GameState`；`to_dict()` 序列化包含 `ruleset`。

---

## 番数与筹码结算

### 大连穷胡规则（`ruleset="dalian"`）

#### 胡牌必要条件（全部同时满足）

| 条件 | 说明 |
|---|---|
| 禁止门清 | 必须至少有一副明副露（碰/吃/杠）才能胡牌 |
| 三色全 | 手牌（含副露）必须同时含条/饼/万三种花色 |
| 幺九 | 含 1 或 9；若手牌有风牌或字牌则豁免 |
| 至少一刻子 | 副露或暗刻至少有一组刻子 |
| 禁手把一 | 副露数 < 4（全吃碰杠不可胡） |
| 三元牌禁刻子 | 中/發/白只能做将，不可碰/组刻子 |

#### 大连番型

| 番型 | 番数 | 条件 |
|---|---|---|
| 基础 | +1 | 始终 |
| 自摸 | +1 | 自摸 |
| 夹胡 | +1 | 荣和时坎张等待（胡牌张为两侧牌的中间张） |
| 庄家 | +1 | 胡牌玩家为庄家 |
| 杠上开花 | +2 | 杠后补牌自摸 |
| 抢杠胡 | +2 | 搶加杠荣和 |
| 摸宝 | +1 | **仅自摸**：自摸宝牌充当野牌替代等待张，或手中有宝牌摸到等待张 |
| 冲宝 | +2 | 胡牌张本身即宝牌（结构性等待张），自摸/点炮均可 |

#### 大连筹码结算

```
unit = min(CHIP_CAP, 2^(总番-1))

荣和（放炮）：放炮者按 han+1 番付钱，其余两家不付
自摸：三家各按自己所受的番数付钱
  未开门（loser 无副露）+1 番（加在输家身上）
  三家门清（三位 loser 均无副露）+1 番（每位输家叠加）
荒庄（流局）：无胡牌筹码结算；杠钱仍正常结算
杠钱结算：无论胡牌与否、无论是谁杠牌，局末统一结算所有玩家的杠（明杠 1×底注/家，暗杠 2×底注/家）
庄家轮换：荒庄时庄不换，闲家胡或普通流局换庄
```

#### 宝牌机制（宝牌/野牌）

- **触发**：第一位进入听牌（需至少 1 副副露）的玩家触发骰子（1–6），从牌墙后端取出第 `dice` 摞（每摞2张）处的牌作为宝牌标识并**取出不放回**；牌墙中其余同种牌（最多3张）才是玩家实际能摸到的野牌
- **效果**：宝牌确定后，任意玩家**自摸到**宝牌可代替所需张完成胡牌（野牌仅限自摸）
- **冲宝**（+2）：宝牌恰好是结构性等待张，摸到/荣和宝牌**直接**胡牌（不靠野牌替代；自摸和点炮均可）
- **摸宝**（+1）：**仅自摸**；摸到宝牌后宝牌充当野牌替代结构性等待张胡牌（非直接等待），或宝牌已在手中、摸到实际等待张胡牌
- **点炮宝牌限制**：别人打出的宝牌**不能**当野牌声索荣和；只有当宝牌恰好是结构性等待张时（冲宝）才可声索
- **区分方法**：`is_winning_hand_dalian(hand, bao_tile=None)` 返回 True → 冲宝；False → 摸宝
- **换宝**：弃牌堆 + 非暗杠副露中宝牌累计 ≥ 3 张时重摇骰子；碰/吃/杠成功后均会触发检测
- **自动检测**：后端在每次出牌后调用 `check_and_trigger_bao()` 检测，无需玩家主动宣听
- **听牌标识**：玩家进入听牌状态后，其区域显示绿色脉冲"听"字 badge（`.tenpai-badge`，区分庄家的金色"庄"badge）
- **听牌后行为**：摸到胡牌张/宝牌→自动胡；其他张→自动打回（不换听）
- **前端**：揭示/换宝时弹出通知（骰子点数 + 听牌者 + 宝牌图样）；顶栏持续显示宝牌 badge；手中宝牌金色发光高亮

---

### 番型（港式规则）

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
| 荒庄阈值 | `game_state.py` `draw_tile` | ≤14 张 | 大连穷胡：牌墙 ≤14 张时荒庄 |

---

## API 接口

### REST（`/api/...`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/rooms` | 获取所有房间列表 |
| POST | `/api/rooms` | 创建新房间（body: `{"name": "...", "ruleset": "hk"|"dalian"}`） |
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
| `game_state` | `players`、`discards`、`phase`、`ruleset`、`cumulative_scores`、`dealer_idx`、`round_wind_idx`、`bao_tile`、`bao_declared`、`bao_revealed_count`、`tenpai_players` |
| `action_required` | `actions`、`drawn_tile` |
| `claim_window` | `tile`、`actions`、`timeout` |
| `game_over` | `winner_id`、`win_ron`、`han_breakdown`、`han_total`、`chip_changes`、`cumulative_scores`、`dealer_idx`、`next_dealer_idx` |
| `bao_declared` | `player_idx`（-1 表示换宝）、`dice`、`bao_tile`、`rerolled`（大连专属：首次揭示或 3 张明牌后换宝） |

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

# E2E 浏览器测试（Playwright）
pip install -r tests/e2e/requirements.txt
playwright install chromium          # 首次需安装 Chromium
playwright install-deps chromium     # Linux 需要（需 root/sudo）
pytest tests/e2e/ -v                 # 全套，约 20 分钟
pytest tests/e2e/test_hk_lobby.py tests/e2e/test_dalian_lobby.py -v  # 快速冒烟，~6s
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
| 后端单元测试 | 412 | tiles/hand/game_state/ai_player/room_manager/routes/dalian_hand/dalian_settlement/dalian_game_state |
| 前端单元测试 | 111 | game.js 纯函数（排序、番数渲染、touch 交互等） |
| 集成测试 | 79 | REST 端点、WS 流程、声索窗口、重开局、Rejoin |
| **E2E 测试（Playwright）** | **28** | 港式/大连大厅、完整游戏流程、结算弹窗、宝牌 badge、听牌标识 |
| **合计** | **630** | |

### E2E 测试设计要点

E2E 测试使用**全 AI 自动完成**策略，无需人工参与：

- `conftest.py` 在随机端口启动后端，注入加速参数（AI 延迟 0.15s、声索超时 1.5s）
- `run_all_ai_game()` 创建房间 → 短暂 WebSocket 连接触发 AI 循环 → 轮询等待 ended
- 游戏结束后，浏览器以重连方式进入游戏页，服务端发送 `game_over(is_reconnect=True)` → 结算弹窗
- 关键设计：kick 玩家必须用非 `ai_player_` 前缀 ID，否则 AI 接管定时器不会触发（服务端安全限制）
- 大连测试额外覆盖：荒庄流局（概率测试）、宝牌 badge、听牌「听」字标识

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
| 28 | 大连 AI 全局流局（AI 从未胡牌） | `ai_player.py` + `websocket.py` | `should_declare_win` 用港式检测无法识别大连胡型；`choose_discard` 港式评分破坏三色全；修复：按 ruleset 分发，新增 `_discard_score_dalian` |
| 29 | 流局弹窗显示「Winner: Player 1」| `game.js` `handleGameOver` | `null + 1 = 1`（JS 特性），流局时 `winner_idx=null` 导致 `winnerName="Player 1"`；修复：先检查 `hasWinner` 再计算 winnerName |
| 30 | 大连荒庄时庄家错误换庄 | `websocket.py` `_handle_game_over` | 流局时统一换庄，未区分大连荒庄庄不换；修复：大连流局不推进 `dealer_idx` |
| 31 | 大连门清可胡（违反规则） | `hand.py` `is_winning_hand_dalian` | 未检查 `n_declared_melds == 0`；修复：首个条件加 `if n_declared_melds == 0: return False` |
| 32 | 自摸冲宝不计番（冲宝条件限定为荣和） | `hand.py` `calculate_han_dalian` | `if ron and winning_tile == bao_tile` 漏掉自摸冲宝；修复：去掉 `ron` 条件，改为 `if winning_tile == bao_tile` |
| 33 | 换宝仅检测弃牌，碰/吃/杠后明牌不触发 | `game_state.py` + `websocket.py` | 旧方案用 `bao_discard_count` 仅在 `discard_tile` 计数；修复：废弃该字段，改用 `_count_bao_revealed()` 统计弃牌堆 + 非暗杠副露，并在碰/吃/杠完成后亦调用 `check_and_maybe_reroll_bao()` |
| 34 | 大连听牌后无任何 UI 标识 | `game.html` + `css/style.css` | 缺少听牌状态展示；修复：新增 `.tenpai-badge` 绿色脉冲样式，game.html 两处标签渲染加入"听"字 badge |
| 35 | 大连听牌后可任意换牌（违反不换听规则） | `game_state.py` `discard_tile` | 未验证出牌后仍在听牌；修复：在 `discard_tile` 中对大连听牌玩家校验 `is_tenpai_dalian(hand_after)` |
| 36 | 大连听牌摸到胡牌张须手动点胡（应自动） | `websocket.py` `_run_ai_turn` | 人类玩家听牌摸牌后走正常流程；修复：检测到听牌状态后，胡牌张→自动 `declare_win`，其他张→自动 `discard_tile(last_drawn_tile)` |
| 37 | `_broadcast_bao_declared` 崩溃导致游戏完全卡死 | `websocket.py` `_broadcast_bao_declared` | `_connections` 结构为 `{pid: ws}`，但代码写成 `for ws,(_, pid) in items()` 导致 unpack 崩溃；修复：改为 `for pid, ws in items()` |
| 38 | 不换听校验用宝牌野牌导致无法出任何牌（死锁） | `game_state.py` `discard_tile` | 不换听检测传 `bao_tile=self.bao_tile`，宝牌野牌误判使所有出牌均被拒绝；修复：改为 `bao_tile=None`（结构性听牌），加安全阀（无合法出牌时移出 tenpai_players） |
| 39 | 未上听玩家可用宝牌野牌胡牌（规则违反） | `game_state.py` 所有胡牌判断 | 所有玩家无差别传入 `bao_tile=self.bao_tile`；规则为「听牌后」方可用宝牌替代；修复：新增 `_effective_bao(player_idx)` 辅助方法，仅对 `tenpai_players` 成员返回宝牌 |
| 40 | 冲宝概率虚高（摸宝被误计为冲宝+2） | `hand.py` `calculate_han_dalian` | `winning_tile == bao_tile` 同时匹配两种情况：① 宝牌直接是结构性等待张（真冲宝+2）② 摸到宝牌后通过野牌替代胡牌（应为摸宝+1）；修复：新增 `is_winning_hand_dalian(bao_tile=None)` 结构性验证，False 则降为摸宝 |
| 41 | 别人打出宝牌可声索荣和（违规：宝牌野牌仅限自摸） | `game_state.py` `get_available_actions`/`declare_win` | 声索检查传 `bao_tile=self._effective_bao(player_idx)`，当打出的牌恰好是宝牌时，`is_winning_hand_dalian` 把它当野牌替代，导致非结构性等待也能荣和；修复：新增 `_effective_bao_for_ron(player_idx, winning_tile)` 辅助方法，winning_tile==bao_tile 时返回 None 禁止野牌替代声索；冲宝（宝牌=结构性等待张）自摸/荣和均合法，不受影响 |
| 42 | 单调（将牌）等待被误判为坎张（夹胡多计 +1） | `hand.py` `_is_kanchan_in_hand` | 手牌含 n-1、n（×2）、n+1 时，函数仅检查双面替代方案，未考虑 n 本身可作将牌（单调等待）；导致如 4条-5条-5条-6条胡第二张5条时被误判为坎张并计夹胡 +1；修复：在双面检查前先判断 winning_tile 是否能作将（full_hand 中 ≥2 张且移除将后剩余牌满足 `_try_extract_melds_dalian`），若能则返回 False（单调非坎张） |
| 47 | 大连 AI 听牌出牌失败后游戏卡死 | `api/websocket.py` `_run_ai_turn` | AI 听牌自动打回 drawn_tile 被 discard_tile 以「不换听」拒绝后，`except ValueError: pass` 落到正常 AI discard；`choose_discard` 又选了破坏听牌的牌，再次抛 ValueError → `return` → 卡死；修复：正常 AI discard 的 except 块对大连听牌玩家逐一尝试备选牌，安全阀保证最终一定能出牌（移出 tenpai_players 后放行） |
| 45 | 大连 AI 贪婪声索第4副副露导致手把一 | `ai_player.py` `decide_claim` | `_hand_progress_score` 以「副露数×30」鼓励声索，AI 在已有3副副露时仍碰/吃/暗杠凑成第4副，触发禁手把一永远无法胡牌；修复：`decide_claim` 大连规则下 `len(melds) >= 3` 时拒绝碰/吃/新增杠；加杠（将已有碰转杠，不新增副露数）仍允许 |
| 44 | 宝牌只「看」不「取出」且取自牌墙前端 | `game_state.py` `check_and_trigger_bao`/`reroll_bao` | 原实现 `bao_tile = wall[(dice-1) % len(wall)]` 存在两个错误：① 取自前端导致触发后1-2轮内必被摸到；② 只读不取出，宝牌仍留在墙中等待被摸（若放后端则荒庄前永远摸不到，若放前端则必然被摸走），均导致宝牌机制失常；真实规则「从牌墙后端取出宝牌揭示，不放回」；修复：新增 `_reveal_bao_from_wall(dice)` 用 `wall.pop(max(0, len(wall)-dice*2))` 从后端取出，牌墙中其余同种牌（最多3张）作为实际野牌供玩家摸取 |
| 43 | 胡牌亮牌时宝牌排在自身花色位置而非替代位置 | `hand.py` `arrange_winning_hand_dalian`（新增）；`game_state.py` `_finalize_win` / `to_dict`；`game.html` 亮牌渲染 | 亮牌用 `sortHandTiles` 按花色/数值排序，宝牌（如 BAMBOO_7 替代 CIRCLES_5）被排到竹子区而非紧邻 CIRCLES_4/6；修复：新增 `arrange_winning_hand_dalian` 按胡牌结构排列（将在前，各副露升序），摸宝场景下宝牌占被替代张的结构位置；`_finalize_win` 计算后存入 `winning_hand_arranged`，`to_dict` 下发；前端赢家亮牌改用服务端排列顺序 |

---

## 已知限制

| 项目 | 当前状态 | 可改进方向 |
|---|---|---|
| 状态持久化 | 纯内存，重启丢失 | Redis / SQLite |
| 玩家认证 | 无，player_id 自生成 | JWT / Session |
| AI 强度 | 启发式贪心 | 蒙特卡洛或规则引擎 |
| 多实例路由 | 同房间玩家须路由到同实例 | WebSocket 粘性路由 / 共享状态 |
| 测试覆盖 | 630 tests | E2E 测试更完善（可用 Playwright 扩展） |
| 横屏适配 | 未专项优化 | 横屏布局调整 |
