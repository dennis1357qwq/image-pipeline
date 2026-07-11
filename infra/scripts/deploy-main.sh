#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:?Set REPO_URL}"
REPO_BRANCH="${REPO_BRANCH:-main}"
PROJECT_DIR="${PROJECT_DIR:-$HOME/image-pipeline}"
DEFAULT_WORKERS="${DEFAULT_WORKERS:-1}"
HEAVY_WORKERS="${HEAVY_WORKERS:-1}"

install_dependencies() {
  sudo apt-get update
  sudo apt-get install -y git ca-certificates curl

  if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
  fi
}

update_repository() {
  if [[ -d "$PROJECT_DIR/.git" ]]; then
    git -C "$PROJECT_DIR" fetch origin
    git -C "$PROJECT_DIR" checkout "$REPO_BRANCH"
    git -C "$PROJECT_DIR" pull --ff-only origin "$REPO_BRANCH"
  else
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$PROJECT_DIR"
  fi
}

validate_environment() {
  local env_file="$PROJECT_DIR/infra/docker/.env.main"

  if [[ ! -f "$env_file" ]]; then
    echo "Missing $env_file"
    echo "Copy .env.main.example to .env.main and fill in the secrets."
    exit 1
  fi
}

deploy() {
  cd "$PROJECT_DIR"

  docker compose \
    --env-file infra/docker/.env.main \
    -f infra/docker/docker-compose.main.yml \
    up -d --build \
    --scale worker-default="$DEFAULT_WORKERS" \
    --scale worker-heavy="$HEAVY_WORKERS"
}

show_status() {
  cd "$PROJECT_DIR"

  docker compose \
    --env-file infra/docker/.env.main \
    -f infra/docker/docker-compose.main.yml \
    ps
}

install_dependencies
update_repository
validate_environment
deploy
show_status