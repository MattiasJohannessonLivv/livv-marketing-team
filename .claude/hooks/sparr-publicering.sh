#!/usr/bin/env bash
# Spärr för Livv Groups AI-marknadsteam.
#
# Körs före varje verktygsanrop (PreToolUse), oavsett agent och instruktion.
# Stoppar publicering och schemaläggning i alla kanaler, ändringar av budgetar,
# bud och kampanjer, radering av filer och skrivning utanför Livv Marketing Ops.
# Godkännande, schemaläggning och publicering kräver att Mattias bekräftar.
#
# Läge: LIVV_UTVECKLING=1 tillåter ändringar i projektfilerna. Annars gäller drift,
# där agenterna bara får skriva lokalt i .arbetsyta/.
#
# Kräver bara bash och python3. Testas med tests/test_sparr.sh.

exec python3 "$(dirname "$0")/sparr.py"
