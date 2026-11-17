#!/usr/bin/env bash
# Startar teamtavlan på http://127.0.0.1:8787 och öppnar den i webbläsaren.
# Tavlan läser bara från SharePoint. Avsluta med Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Hittar ingen .env. Kopiera .env.example till .env och fyll i värdena." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

PORT="${TAVLA_PORT:-8787}"
if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "http://127.0.0.1:$PORT") &
fi
exec python3 tavla/server.py
