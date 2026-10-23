#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Silexa Bot — One-Command VPS Build & Deployment Script
# Workflow:
#   1. On local machine: git push origin main
#   2. On VPS:           ./deploy.sh
# ==============================================================================

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

SERVICE_NAME="silexa-bot"
SYSTEMD_UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
BRANCH="${DEPLOY_BRANCH:-main}"
PID_FILE="${APP_DIR}/data/bot.pid"
LOG_FILE="${APP_DIR}/logs/bot.log"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        err "Root privileges or sudo required for: $*"
        return 1
    fi
}

is_docker_active() {
    command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${SERVICE_NAME}$"
}

usage() {
    cat <<EOF
Usage: ./deploy.sh [OPTION]

Options:
  (no args)     Pull latest code from GitHub, update dependencies, and restart bot
  --systemd     Deploy using Python virtualenv (.venv) + systemd service (default)
  --docker      Deploy and rebuild container using Docker Compose
  --status      Check running status of Silexa Bot
  --logs        Follow live logs (Ctrl+C to exit)
  --stop        Stop Silexa Bot
  --help        Show this help message
EOF
}

check_env() {
    mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs"
    if [ ! -f "${APP_DIR}/.env" ]; then
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
        warn "Created .env from .env.example."
        err "Please edit ${APP_DIR}/.env and set your DISCORD_TOKEN, then re-run ./deploy.sh"
        exit 1
    fi
    if grep -q "your_discord_bot_token_here" "${APP_DIR}/.env"; then
        err "DISCORD_TOKEN in ${APP_DIR}/.env is still set to the placeholder value!"
        exit 1
    fi
}

git_update() {
    if [ -d "${APP_DIR}/.git" ]; then
        info "Fetching latest changes from origin/${BRANCH}..."
        git fetch origin "$BRANCH"
        LOCAL_REV="$(git rev-parse HEAD)"
        REMOTE_REV="$(git rev-parse "origin/${BRANCH}")"
        if [ "$LOCAL_REV" != "$REMOTE_REV" ]; then
            info "Updating working tree (${LOCAL_REV:0:7} -> ${REMOTE_REV:0:7})..."
            git pull --ff-only origin "$BRANCH"
            chmod +x "${APP_DIR}/deploy.sh"
            ok "Repository updated to $(git rev-parse --short HEAD)."
        else
            ok "Already up to date at $(git rev-parse --short HEAD)."
        fi
    else
        warn "Not a git repository; skipping git pull."
    fi
}

deploy_docker() {
    check_env
    git_update
    info "Building and starting Docker container (${SERVICE_NAME})..."
    docker compose up -d --build --remove-orphans
    ok "Docker deployment complete!"
    docker compose ps
}

install_systemd_unit() {
    local current_user
    current_user="$(id -un)"
    info "Installing systemd service: ${SYSTEMD_UNIT} (User: ${current_user})..."
    local tmp_unit
    tmp_unit="$(mktemp)"
    cat >"$tmp_unit" <<EOF
[Unit]
Description=Silexa Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${current_user}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    run_privileged mv "$tmp_unit" "$SYSTEMD_UNIT"
    run_privileged chmod 644 "$SYSTEMD_UNIT"
    run_privileged systemctl daemon-reload
    run_privileged systemctl enable "$SERVICE_NAME"
    ok "Systemd service '${SERVICE_NAME}' installed and enabled on boot."
}

deploy_systemd() {
    check_env
    git_update

    if [ ! -d "${APP_DIR}/.venv" ]; then
        info "Creating Python virtual environment (.venv)..."
        python3 -m venv "${APP_DIR}/.venv"
    fi

    info "Installing/updating Python dependencies..."
    "${APP_DIR}/.venv/bin/pip" install -q --upgrade pip
    "${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"

    info "Running pre-flight syntax verification..."
    "${APP_DIR}/.venv/bin/python" -m py_compile \
        bot.py config.py utils/*.py cogs/*.py
    ok "Syntax verification passed."

    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        if [ ! -f "$SYSTEMD_UNIT" ]; then
            install_systemd_unit
        fi
        info "Restarting systemd service '${SERVICE_NAME}'..."
        run_privileged systemctl restart "$SERVICE_NAME"
        sleep 2
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            ok "Silexa Bot is online and running via systemd!"
            systemctl status "$SERVICE_NAME" --no-pager -n 8 || true
        else
            err "Service failed to start! Check logs with: ./deploy.sh --logs"
            run_privileged journalctl -u "$SERVICE_NAME" -n 25 --no-pager || true
            exit 1
        fi
    else
        warn "systemd not detected; starting Silexa Bot in background (nohup)..."
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            info "Stopping previous process (PID $(cat "$PID_FILE"))..."
            kill "$(cat "$PID_FILE")" || true
            sleep 1
        fi
        nohup "${APP_DIR}/.venv/bin/python" "${APP_DIR}/bot.py" >>"$LOG_FILE" 2>&1 &
        echo $! >"$PID_FILE"
        sleep 2
        if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            ok "Silexa Bot started in background (PID $(cat "$PID_FILE"), log: ${LOG_FILE})."
        else
            err "Bot exited prematurely! Last log lines:"
            tail -n 20 "$LOG_FILE" || true
            exit 1
        fi
    fi
}

show_status() {
    if is_docker_active; then
        docker compose ps
    elif command -v systemctl >/dev/null 2>&1 && [ -f "$SYSTEMD_UNIT" ]; then
        systemctl status "$SERVICE_NAME" --no-pager
    elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        ok "Silexa Bot is running via PID $(cat "$PID_FILE")."
    else
        warn "Silexa Bot is not currently running."
    fi
}

show_logs() {
    if is_docker_active; then
        docker compose logs -f --tail=50
    elif command -v systemctl >/dev/null 2>&1 && [ -f "$SYSTEMD_UNIT" ]; then
        run_privileged journalctl -u "$SERVICE_NAME" -f -n 50
    elif [ -f "$LOG_FILE" ]; then
        tail -f -n 50 "$LOG_FILE"
    else
        warn "No logs found."
    fi
}

stop_bot() {
    if is_docker_active; then
        info "Stopping Docker container..."
        docker compose down
        ok "Stopped."
    elif command -v systemctl >/dev/null 2>&1 && [ -f "$SYSTEMD_UNIT" ]; then
        info "Stopping systemd service '${SERVICE_NAME}'..."
        run_privileged systemctl stop "$SERVICE_NAME"
        ok "Stopped."
    elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")" && rm -f "$PID_FILE"
        ok "Stopped background process."
    else
        warn "Bot is not running."
    fi
}

MODE="${1:-auto}"
case "$MODE" in
    auto)
        if is_docker_active; then
            deploy_docker
        else
            deploy_systemd
        fi
        ;;
    --systemd)
        deploy_systemd
        ;;
    --docker)
        deploy_docker
        ;;
    --status)
        show_status
        ;;
    --logs)
        show_logs
        ;;
    --stop)
        stop_bot
        ;;
    --help|-h)
        usage
        ;;
    *)
        err "Unknown option: $MODE"
        usage
        exit 1
        ;;
esac
