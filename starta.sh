#!/usr/bin/env bash
# Startar Livv Groups AI-marknadsteam med A0 som huvudsession.
#   ./starta.sh                 drift: agenterna skriver bara i SharePoint och .arbetsyta/
#   ./starta.sh --utveckling    utvecklingsläge: projektfilerna får ändras
# Övriga argument skickas vidare till claude, till exempel -p "Veckoplan".
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

export LIVV_UTVECKLING=0
if [ "${1:-}" = "--utveckling" ]; then
  export LIVV_UTVECKLING=1
  shift
  echo "Utvecklingsläge: projektfilerna kan ändras."
fi

# I drift hämtas senaste godkända versionen från main innan teamet startar.
# Det görs här, utanför Claude, så att spärren aldrig behöver tillåta git pull.
if [ "$LIVV_UTVECKLING" = "0" ]; then
  source ./hamta.sh
fi

mkdir -p .arbetsyta
exec claude "$@"
