# ── 麻将游戏 (Mahjong) — Cloud Run Dockerfile ──────────────────────────────
# 单阶段构建：FastAPI + Uvicorn，同时 serve 前端静态文件
# Cloud Run 默认监听 PORT 环境变量（默认 8080）
# ---------------------------------------------------------------------------

FROM python:3.11-slim

# 不生成 .pyc 文件；关闭 Python 输出缓冲（日志实时可见）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先复制 requirements 利用 Docker layer cache
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 复制后端源码
COPY backend/ ./backend/

# 复制前端静态文件（FastAPI 通过 StaticFiles 挂载）
COPY frontend/ ./frontend/

# Cloud Run 会注入 PORT 环境变量（默认 8080）
# uvicorn 从 /app 目录以 backend.main:app 方式启动
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
