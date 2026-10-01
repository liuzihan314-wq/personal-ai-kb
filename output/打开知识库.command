#!/bin/zsh

# 双击此文件即可启动或打开本地知识库网页。
set -u

PROJECT_DIR="${0:A:h:h}"
APP_FILE="$PROJECT_DIR/src/pkb/ui/app.py"
LOG_DIR="$PROJECT_DIR/runtime/logs"
URL="http://127.0.0.1:8501/"
HEALTH_URL="http://127.0.0.1:8501/_stcore/health"
PID_FILE="$PROJECT_DIR/runtime/knowledge-base-ui.pid"
MODE_FILE="$PROJECT_DIR/runtime/knowledge-base-ui.mode"
REVISION_FILE="$PROJECT_DIR/runtime/knowledge-base-ui.revision"
MODE_SIGNATURE="local-owner-v1"
CURRENT_REVISION="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || true)"

# 优先使用 uv 维护的 .venv；若不存在则回退到旧 runtime/python-venv。
if [[ -x "$PROJECT_DIR/.venv/bin/streamlit" ]]; then
  VENV_DIR="$PROJECT_DIR/.venv"
elif [[ -x "$PROJECT_DIR/runtime/python-venv/bin/streamlit" ]]; then
  VENV_DIR="$PROJECT_DIR/runtime/python-venv"
else
  osascript -e 'display alert "知识库无法启动" message "项目运行环境未找到。请在 Codex 中重新完成本地环境安装。" as critical'
  exit 1
fi

STREAMLIT="$VENV_DIR/bin/streamlit"

# 本机主人入口只监听回环地址，并明确覆盖 .env 中可能启用的共享认证。
# 公网分享必须使用独立的 invite 部署配置，不能运行此本机启动器。
export PKB_AUTH_ENABLED=false
export PKB_AUTH_MODE=cloudflare

# 使用项目环境自带的 CA 证书，避免本机代理证书导致 HTTPS 校验失败。
export SSL_CERT_FILE="$("$VENV_DIR/bin/python" -c 'import certifi; print(certifi.where())')"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"

START_SERVER=true
if /usr/bin/curl --silent --fail --max-time 1 "$HEALTH_URL" >/dev/null 2>&1; then
  MANAGED_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  MANAGED_MODE="$(cat "$MODE_FILE" 2>/dev/null || true)"
  MANAGED_COMMAND=""
  if [[ "$MANAGED_PID" == <-> ]]; then
    MANAGED_COMMAND="$(ps -p "$MANAGED_PID" -o command= 2>/dev/null || true)"
  fi
  if [[ "$MANAGED_MODE" != "$MODE_SIGNATURE" || "$MANAGED_COMMAND" != *"$APP_FILE"* ]]; then
    osascript -e 'display alert "知识库端口已被其他实例占用" message "8501 端口上的服务不是当前 output 启动器创建的本机主人实例。请先在 Codex 中停止旧实例，再重新双击打开。" as critical'
    exit 1
  fi
  MANAGED_REVISION="$(cat "$REVISION_FILE" 2>/dev/null || true)"
  if [[ -n "$CURRENT_REVISION" && "$MANAGED_REVISION" != "$CURRENT_REVISION" ]]; then
    kill -TERM "$MANAGED_PID"
    for _ in {1..20}; do
      if ! /usr/bin/curl --silent --fail --max-time 1 "$HEALTH_URL" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if /usr/bin/curl --silent --fail --max-time 1 "$HEALTH_URL" >/dev/null 2>&1; then
      osascript -e 'display alert "知识库旧实例未能停止" message "请在 Codex 中检查 8501 端口上的本机服务，再重新双击打开。" as critical'
      exit 1
    fi
  else
    START_SERVER=false
  fi
fi

if [[ "$START_SERVER" == true ]]; then
  mkdir -p "$LOG_DIR"
  cd "$PROJECT_DIR"
  nohup "$STREAMLIT" run "$APP_FILE" \
    --server.headless true \
    --server.address 127.0.0.1 \
    --server.port 8501 \
    --server.runOnSave true \
    > "$LOG_DIR/knowledge-base-ui.log" 2>&1 &
  SERVER_PID=$!
  mkdir -p "$PROJECT_DIR/runtime"
  print -r -- "$SERVER_PID" > "$PID_FILE"
  print -r -- "$MODE_SIGNATURE" > "$MODE_FILE"
  print -r -- "$CURRENT_REVISION" > "$REVISION_FILE"

  for _ in {1..20}; do
    if /usr/bin/curl --silent --fail --max-time 1 "$HEALTH_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if /usr/bin/curl --silent --fail --max-time 1 "$HEALTH_URL" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

osascript -e "display alert \"知识库未能启动\" message \"请查看运行日志：$LOG_DIR/knowledge-base-ui.log\" as critical"
exit 1
