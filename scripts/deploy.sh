#!/usr/bin/env bash
# ============================================================
# MiroFish 电商预演平台 — 一键部署 / 管理脚本
#
# 用法：
#   bash scripts/deploy.sh setup    # 首次部署：环境检查 + 容器 + 依赖 + 构建 + 验证
#   bash scripts/deploy.sh start    # 启动 API(gunicorn) + Worker
#   bash scripts/deploy.sh stop     # 停止
#   bash scripts/deploy.sh status   # 健康检查
#   bash scripts/deploy.sh verify   # 全链路验证（图谱冒烟）
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN_DIR="$ROOT/backend/uploads/run"
# 项目自持 uv 缓存（避免系统缓存目录权限问题）
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uv-cache}"
mkdir -p "$RUN_DIR" "$UV_CACHE_DIR"

c_info()  { echo -e "\033[36m[info]\033[0m $*"; }
c_ok()    { echo -e "\033[32m[ ok ]\033[0m $*"; }
c_warn()  { echo -e "\033[33m[warn]\033[0m $*"; }
c_fail()  { echo -e "\033[31m[fail]\033[0m $*"; exit 1; }

check_prereqs() {
  command -v docker >/dev/null || c_fail "需要 Docker（https://docker.com）"
  docker info >/dev/null 2>&1 || c_fail "Docker daemon 未运行，请启动 Docker/OrbStack"
  command -v uv >/dev/null || c_fail "需要 uv（curl -LsSf https://astral.sh/uv/install.sh | sh）"
  command -v node >/dev/null || c_warn "未检测到 node——跳过前端构建（可只部署 API）"
  c_ok "依赖检查通过"
}

ensure_env() {
  cd "$ROOT"
  if [ ! -f .env ]; then
    cp .env.example .env
    NEO_PW=$(openssl rand -hex 12 2>/dev/null || head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')
    sed -i.bak "s|NEO4J_PASSWORD=.*|NEO4J_PASSWORD=$NEO_PW|" .env && rm -f .env.bak
    c_ok "已生成 .env（NEO4J_PASSWORD 已随机生成）"
    c_warn "请编辑 .env 填入：LLM_API_KEY / 支付渠道密钥 / CORS_ORIGINS"
  else
    c_ok ".env 已存在，跳过生成"
  fi
  # 生产安全检查
  if grep -q "^ALLOW_DEV_PAYMENT=true" .env; then
    c_warn "ALLOW_DEV_PAYMENT=true 处于开启状态——仅限本地开发！生产必须删除该行"
  fi
  if grep -q "^PAYMENT_MODE=dev" .env; then
    c_warn "PAYMENT_MODE=dev：未接入真实支付渠道（生产应设为 stripe/creem 等）"
  fi
}

start_containers() {
  cd "$ROOT"
  c_info "启动 Neo4j + Ollama 容器..."
  docker compose up -d neo4j ollama
  sleep 3
  # 等待 Neo4j 健康
  for i in $(seq 1 30); do
    st=$(docker inspect --format '{{.State.Health.Status}}' mirofish-neo4j 2>/dev/null || echo unknown)
    [ "$st" = "healthy" ] && break
    sleep 2
  done
  [ "$st" = "healthy" ] && c_ok "Neo4j healthy" || c_fail "Neo4j 未就绪（$st）"
  # 拉取 embedding 模型（幂等，已存在则秒过）
  c_info "确保 embedding 模型存在..."
  docker exec mirofish-ollama ollama pull qwen3-embedding:0.6b >/dev/null 2>&1 \
    && c_ok "qwen3-embedding:0.6b 就绪" || c_warn "模型拉取失败，请手动执行：docker exec mirofish-ollama ollama pull qwen3-embedding:0.6b"
}

install_deps() {
  cd "$BACKEND"
  c_info "安装后端依赖 (uv sync)..."
  uv sync --extra payments >/dev/null 2>&1 || uv sync
  c_ok "后端依赖就绪"
  if command -v node >/dev/null; then
    cd "$FRONTEND"
    c_info "安装前端依赖并构建..."
    npm install --no-audit --no-fund >/dev/null 2>&1
    npm run build >/dev/null 2>&1
    c_ok "前端构建完成（dist/ 由后端直接托管）"
  fi
}

run_verification() {
  cd "$BACKEND"
  c_info "运行测试套件..."
  uv run pytest tests/ -q | tail -1
  c_info "图谱全链路冒烟..."
  uv run python scripts/validate_graphiti_full_loop.py | grep -E "✓|✅|✗" | tail -3
}

start_services() {
  cd "$BACKEND"
  mkdir -p "$RUN_DIR"
  c_info "启动 API（gunicorn，2进程×4线程，:5001）..."
  uv run gunicorn -w 2 --threads 4 -b 0.0.0.0:5001 \
    --daemon --pid "$RUN_DIR/api.pid" \
    --access-logfile "$RUN_DIR/api-access.log" \
    --error-logfile "$RUN_DIR/api-error.log" \
    "app:create_app()"
  sleep 2
  curl -sf -m 5 http://localhost:5001/health >/dev/null && c_ok "API 已启动 (:5001)" \
    || c_fail "API 启动失败，查看 $RUN_DIR/api-error.log"

  c_info "启动 Worker..."
  nohup uv run python -m app.worker --concurrency "${WORKER_CONCURRENCY:-1}" \
    > "$RUN_DIR/worker.log" 2>&1 &
  echo $! > "$RUN_DIR/worker.pid"
  sleep 1
  c_ok "Worker 已启动 (pid $(cat "$RUN_DIR/worker.pid"))"

  c_ok "完成！门户地址: http://localhost:5001/orders （前端页面同端口）"
}

stop_services() {
  if [ -f "$RUN_DIR/api.pid" ]; then kill "$(cat "$RUN_DIR/api.pid")" 2>/dev/null && rm "$RUN_DIR/api.pid"; fi
  if [ -f "$RUN_DIR/worker.pid" ]; then kill "$(cat "$RUN_DIR/worker.pid")" 2>/dev/null && rm "$RUN_DIR/worker.pid"; fi
  # 兜底清理同名进程
  pkill -f "gunicorn.*app:create_app" 2>/dev/null || true
  pkill -f "python -m app.worker" 2>/dev/null || true
  c_ok "服务已停止"
}

show_status() {
  echo "== 容器 =="
  docker ps --filter name=mirofish --format '{{.Names}}: {{.Status}}' 2>/dev/null || true
  echo "== 服务 =="
  curl -sf -m 3 http://localhost:5001/health >/dev/null && echo "API: 运行中" || echo "API: 未运行"
  pgrep -f "python -m app.worker" >/dev/null && echo "Worker: 运行中" || echo "Worker: 未运行"
  echo "== 订单队列 =="
  cd "$BACKEND" && uv run python - <<'PY' 2>/dev/null || true
from app.models.order import OrderStore
from collections import Counter
store = OrderStore()
orders = store.list_orders(limit=500)
counts = Counter(o["status"] for o in orders)
print({k: v for k, v in sorted(counts.items())} or "（空）")
PY
}

verify_all() {
  cd "$BACKEND"
  uv run python scripts/validate_graphiti_integration.py 2>&1 | grep -E "✓|✅|✗" | tail -8
}

case "${1:-help}" in
  setup)   check_prereqs; ensure_env; start_containers; install_deps; run_verification; c_ok "部署完成！执行 bash scripts/deploy.sh start 启动服务";;
  start)   start_services;;
  stop)    stop_services;;
  status)  show_status;;
  verify)  verify_all;;
  restart) stop_services; start_services;;
  *)       echo "用法: bash scripts/deploy.sh {setup|start|stop|restart|status|verify}";;
esac
