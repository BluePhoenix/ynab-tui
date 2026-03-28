#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_FILE="${YNAB_TUI_SECRETS_FILE:-$ROOT_DIR/secrets.env}"
DATA_DIR="${YNAB_TUI_DATA_DIR:-$ROOT_DIR/.ynab-tui}"
UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.uv-cache}"

if ! command -v sops >/dev/null 2>&1; then
  echo "sops is required but not installed." >&2
  echo "Install it with: brew install sops age" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but not installed." >&2
  echo "Install it with: brew install uv" >&2
  exit 1
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Encrypted secrets file not found: $SECRETS_FILE" >&2
  echo "Create it as a dotenv file and encrypt it with sops." >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$UV_CACHE_DIR"

set -a
# shellcheck disable=SC1090
source <(sops --decrypt "$SECRETS_FILE")
set +a

export YNAB_TUI_DATA_DIR="$DATA_DIR"
export UV_CACHE_DIR="$UV_CACHE_DIR"

exec uv run ynab-tui "$@"
