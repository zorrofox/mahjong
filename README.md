# 麻将游戏 / Mahjong

基于浏览器的多人麻将游戏，支持 1–4 名真人玩家，空位由 AI 自动填补。

A browser-based multiplayer Mahjong game. Supports 1–4 human players per room; empty seats are filled by AI.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![Tests](https://img.shields.io/badge/tests-327%20passed-brightgreen)

---

## 功能特性 / Features

- 标准中国麻将规则（144 张牌，含花牌季牌）
- 实时多人对战（WebSocket）
- AI 自动填补空位，启发式出牌与声索决策
- 声索优先级：胡 > 碰/杠 > 吃
- 自摸与荣和均支持
- 传统麻将牌视觉风格：汉字数字（一～九）+ 花色名（萬/条/饼），象牙骨色 3D 浮雕牌面
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
│   ├── game/          # 游戏引擎（牌型、胡牌、状态机、AI）
│   ├── api/           # FastAPI 路由 + WebSocket 处理
│   └── tests/         # 后端单元测试（233 tests）
├── frontend/
│   ├── js/            # 大厅 + 游戏客户端
│   └── tests/         # 前端单元测试（56 tests）
└── tests/
    └── integration/   # REST + WebSocket 集成测试（38 tests）
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
| 字体 | Noto Serif SC（Google Fonts，传统汉字渲染） |
| 测试 | pytest + Vitest |

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

详细文档见 [CLAUDE.md](CLAUDE.md)。
