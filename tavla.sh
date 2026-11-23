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

# Senaste godkända versionen från main, innan tavlan startar
source ./hamta.sh

PORT="${TAVLA_PORT:-8787}"

# Körs en äldre tavla redan stoppas den, så att den nya koden används.
# Ett annat program på porten stoppas aldrig: då avslutas skriptet med en förklaring.
if command -v lsof >/dev/null 2>&1; then
  for pid in $(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true); do
    if ps -o command= -p "$pid" 2>/dev/null | grep -q "tavla/server.py"; then
      echo "En äldre tavla körs redan. Stoppar den och startar den nya."
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        lsof -ti "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
        sleep 1
      done
    else
      echo "Port $PORT används av ett annat program ($(ps -o comm= -p "$pid" 2>/dev/null)). Stäng det, eller starta med TAVLA_PORT=8788 ./tavla.sh" >&2
      exit 1
    fi
  done
fi
if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "http://127.0.0.1:$PORT") &
fi
exec python3 tavla/server.py
