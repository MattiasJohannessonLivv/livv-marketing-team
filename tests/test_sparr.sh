#!/usr/bin/env bash
# Tester för Livv-spärren. Matar hooken med påhittade anrop och kontrollerar beslutet.
# Kör: bash tests/test_sparr.sh
# Inget anrop når SharePoint eller någon kanal: hooken läser bara JSON.

set -u
PROJEKT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$PROJEKT/.claude/hooks/sparr-publicering.sh"
export CLAUDE_PROJECT_DIR="$PROJEKT"
fel=0
antal=0

kontrollera() {
  local forvantat="$1" beskrivning="$2" json="$3" lage="${4:-0}"
  local utdata beslut
  utdata="$(printf '%s' "$json" | LIVV_UTVECKLING="$lage" bash "$HOOK")"
  beslut="$(printf '%s' "$utdata" | python3 -c 'import json,sys
t=sys.stdin.read().strip()
print(json.loads(t)["hookSpecificOutput"]["permissionDecision"] if t else "tillat")')"
  antal=$((antal + 1))
  if [ "$beslut" = "$forvantat" ]; then
    echo "ok     $beskrivning"
  else
    echo "FEL    $beskrivning: väntade $forvantat, fick $beslut"
    fel=$((fel + 1))
  fi
}

mcp() { printf '{"tool_name":"mcp__%s","tool_input":%s,"agent_type":"%s"}' "$1" "$2" "${3:-}"; }

echo "Publicering, budget och kampanjer"
kontrollera deny  "LinkedIn-inlägg via claude.ai-koppling"  "$(mcp linkedin__create_post '{"text":"Hej"}')"
kontrollera deny  "Schemaläggning i HubSpot"                 "$(mcp plugin_marketing_hubspot__schedule_email '{}')"
kontrollera deny  "Budgetändring i Meta"                    "$(mcp meta__update_campaign_budget '{"budget":100}')"
kontrollera deny  "Bud i Google Ads"                        "$(mcp google_ads__set_bid '{}')"
kontrollera deny  "Mejl via Microsoft 365"                  "$(mcp Microsoft_365__outlook_create_draft '{}')"
kontrollera deny  "Okänt verktyg i SharePoint-servern"      "$(mcp sharepoint__delete_item '{}')"

echo "SharePoint-servern"
kontrollera tillat "Läsa en fil"                             "$(mcp sharepoint__las_fil '{"sokvag":"00_Underlag"}')"
kontrollera tillat "A0 skapar brief"                         "$(mcp sharepoint__skapa_brief '{"varumarke":"Livv"}')"
kontrollera tillat "A3 flyttar till Granskning"              "$(mcp sharepoint__flytta_objekt '{"till_status":"Granskning"}' a3-granskare)"
kontrollera ask   "Flytt till Godkänd kräver Mattias"        "$(mcp sharepoint__flytta_objekt '{"till_status":"Godkänd","filnamn":"x"}')"
kontrollera ask   "Flytt till Publicerad kräver Mattias"     "$(mcp sharepoint__flytta_objekt '{"till_status":"Publicerad"}')"
kontrollera ask   "godkand_av i registret kräver Mattias"    "$(mcp sharepoint__register_uppdatera '{"objekt_id":"LIVV-2026-0001","falt":{"godkand_av":"Mattias Johannesson"}}')"
kontrollera ask   "Status Schemalagd kräver Mattias"         "$(mcp sharepoint__register_uppdatera '{"objekt_id":"LIVV-2026-0001","falt":{"status":"Schemalagd"}}')"
kontrollera tillat "A3 sätter a3_utfall"                     "$(mcp sharepoint__register_uppdatera '{"objekt_id":"LIVV-2026-0001","falt":{"a3_utfall":"Godkänd"}}' a3-granskare)"

echo "Rollspärrar"
kontrollera deny  "A3 kan inte skapa brief"                 "$(mcp sharepoint__skapa_brief '{}' a3-granskare)"
kontrollera deny  "A3 kan inte skapa nytt objekt"           "$(mcp sharepoint__register_ny_rad '{}' a3-granskare)"
kontrollera deny  "A3 kan inte flytta till Godkänd"         "$(mcp sharepoint__flytta_objekt '{"till_status":"Godkänd"}' a3-granskare)"
kontrollera deny  "A4 kan inte skapa brief"                 "$(mcp sharepoint__skapa_brief '{}' a4-contentcreator)"
kontrollera deny  "A4 kan inte flytta"                      "$(mcp sharepoint__flytta_objekt '{"till_status":"Granskning"}' a4-contentcreator)"
kontrollera tillat "A4 sparar utkast"                        "$(mcp sharepoint__spara_utkast '{}' a4-contentcreator)"

echo "Radering och nätverk"
kontrollera deny  "rm"                                       '{"tool_name":"Bash","tool_input":{"command":"rm -rf .arbetsyta"}}' 1
kontrollera deny  "find -delete"                             '{"tool_name":"Bash","tool_input":{"command":"find . -name x -delete"}}' 1
kontrollera deny  "git clean"                                '{"tool_name":"Bash","tool_input":{"command":"git clean -fd"}}' 1
kontrollera deny  "git push --force"                         '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' 1
kontrollera deny  "curl mot LinkedIn"                        '{"tool_name":"Bash","tool_input":{"command":"curl -X POST https://api.linkedin.com/v2/ugcPosts"}}' 1
kontrollera deny  "Webbsök"                                  '{"tool_name":"WebSearch","tool_input":{"query":"x"}}'
kontrollera deny  "Läsa .env"                                '{"tool_name":"Read","tool_input":{"file_path":".env"}}'

echo "Lokala filer i drift"
kontrollera tillat "Skriva i .arbetsyta"                     "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$PROJEKT/.arbetsyta/x.md\"}}"
kontrollera deny  "Ändra CLAUDE.md i drift"                 "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$PROJEKT/CLAUDE.md\"}}"
kontrollera deny  "Skriva utanför projektet"                '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x.md"}}'
kontrollera deny  "Smita ut via ../"                        "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$PROJEKT/.arbetsyta/../CLAUDE.md\"}}"
kontrollera tillat "Läsande skal"                            '{"tool_name":"Bash","tool_input":{"command":"ls -la | grep md && git status"}}'
kontrollera deny  "Skrivande skal i drift"                  '{"tool_name":"Bash","tool_input":{"command":"python3 skript.py"}}'
kontrollera deny  "Omdirigering ut ur arbetsytan"           '{"tool_name":"Bash","tool_input":{"command":"echo x > CLAUDE.md"}}'

kontrollera tillat "git ls-remote i drift"                   '{"tool_name":"Bash","tool_input":{"command":"git ls-remote origin"}}'
kontrollera tillat "git fetch i drift"                       '{"tool_name":"Bash","tool_input":{"command":"git fetch origin fas-1"}}'
kontrollera deny  "git fetch --upload-pack i drift"         '{"tool_name":"Bash","tool_input":{"command":"git fetch --upload-pack=sh origin"}}'
kontrollera deny  "git ls-remote -u i drift"                '{"tool_name":"Bash","tool_input":{"command":"git ls-remote -u sh origin"}}'
kontrollera deny  "git fetch med tvingad refspec"           '{"tool_name":"Bash","tool_input":{"command":"git fetch origin +main:main"}}'
kontrollera deny  "git fetch --force"                       '{"tool_name":"Bash","tool_input":{"command":"git fetch --force origin"}}'
kontrollera deny  "git pull i drift"                        '{"tool_name":"Bash","tool_input":{"command":"git pull origin fas-1"}}'
kontrollera deny  "gh i drift"                              '{"tool_name":"Bash","tool_input":{"command":"gh pr list"}}'
kontrollera deny  "gh efter läsande kommando i drift"       '{"tool_name":"Bash","tool_input":{"command":"git status && gh pr list"}}'

echo "Utvecklingsläge"
kontrollera tillat "Ändra CLAUDE.md"                         "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$PROJEKT/CLAUDE.md\"}}" 1
kontrollera deny  "Ändra .env"                              "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$PROJEKT/.env\"}}" 1
kontrollera deny  "Skriva utanför projektet"                '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x.md"}}' 1
kontrollera tillat "gh pr list"                              '{"tool_name":"Bash","tool_input":{"command":"gh pr list"}}' 1
kontrollera tillat "gh api"                                  '{"tool_name":"Bash","tool_input":{"command":"gh api repos/x/y/pulls"}}' 1
kontrollera deny  "gh repo delete"                          '{"tool_name":"Bash","tool_input":{"command":"gh repo delete x/y --yes"}}' 1
kontrollera tillat "git fetch"                               '{"tool_name":"Bash","tool_input":{"command":"git fetch origin"}}' 1
kontrollera deny  "curl även i utvecklingsläge"             '{"tool_name":"Bash","tool_input":{"command":"curl https://example.com"}}' 1
kontrollera tillat "Köra testerna"                           '{"tool_name":"Bash","tool_input":{"command":"python3 -m unittest discover -s tests"}}' 1

echo
echo "$((antal - fel)) av $antal gick igenom."
[ "$fel" -eq 0 ]
