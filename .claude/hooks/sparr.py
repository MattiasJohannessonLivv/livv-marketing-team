"""Logiken i Livv-spärren. Anropas av sparr-publicering.sh, se kommentarerna där."""
import json, os, re, shlex, sys

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

verktyg = data.get("tool_name", "") or ""
inp = data.get("tool_input", {}) or {}
# Rollen kommer från Claude Code (agent_type) eller från agentens egen hook (LIVV_ROLL).
agent = data.get("agent_type", "") or os.environ.get("LIVV_ROLL", "")
utveckling = os.environ.get("LIVV_UTVECKLING") == "1"
projekt = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
arbetsyta = os.path.join(projekt, ".arbetsyta")


def svar(beslut, skal):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": beslut,
        "permissionDecisionReason": "Livv-spärren: " + skal,
    }}, ensure_ascii=False))
    sys.exit(0)


def stoppa(skal):
    svar("deny", skal)


def fraga(skal):
    svar("ask", skal)


# 1. MCP: bara kända verktyg i SharePoint-servern släpps igenom ------------------
SHAREPOINT = {
    "lista_mapp", "las_fil", "skapa_brief", "spara_utkast", "spara_rapport",
    "flytta_objekt", "register_las", "register_ny_rad", "register_uppdatera", "logga",
    "spara_bildbrief", "visa_bild",
}
FARLIGA_ORD = re.compile(
    r"publish|post|schedul|send|share|tweet|reply|comment|boost|budget|bid|"
    r"campaign|adset|ad_set|ads_|_ad_|creative|delete|remove|trash|purge|"
    r"permission|invite|rename",
    re.I,
)
MANSKLIG_STATUS = {"Godkänd", "Schemalagd", "Publicerad"}
MANSKLIGA_FALT = {"godkand_av", "godkand_datum", "publicerad_datum", "plattforms_id", "url"}

if verktyg.startswith("mcp__"):
    if not verktyg.startswith("mcp__sharepoint__"):
        stoppa(f"{verktyg} är inte tillåtet. I fas 1 får teamet bara använda SharePoint-servern. "
               "Ingen agent publicerar eller ändrar budgetar, bud eller kampanjer.")
    namn = verktyg[len("mcp__sharepoint__"):]
    if namn not in SHAREPOINT or FARLIGA_ORD.search(namn):
        stoppa(f"{namn} är inget godkänt verktyg i SharePoint-servern.")

    # Rollspärrar, utöver verktygslistorna i .claude/agents/
    if agent == "a3-granskare":
        if namn in {"skapa_brief", "register_ny_rad", "spara_utkast", "spara_rapport", "spara_bildbrief"}:
            stoppa("A3 skapar aldrig briefer, utkast, rapporter eller nya objekt.")
        if namn == "flytta_objekt" and inp.get("till_status") not in {"Granskning", "Avvisad"}:
            stoppa("A3 får bara flytta till Granskning eller Avvisad.")
    if agent == "a2-researcher":
        if namn in {"skapa_brief", "register_ny_rad", "register_uppdatera", "spara_utkast", "flytta_objekt", "spara_bildbrief"}:
            stoppa("A2 läser och analyserar. Briefer, utkast, flyttar och ändringar i registret sköts av andra roller.")
    if agent == "a4-contentcreator":
        if namn in {"skapa_brief", "register_ny_rad", "flytta_objekt", "spara_rapport", "spara_bildbrief"}:
            stoppa("A4 skriver bara utkast. Briefer, nya objekt och flyttar sköts av andra roller.")

    # Mänsklig grind: Mattias måste bekräfta
    if namn == "flytta_objekt" and inp.get("till_status") in MANSKLIG_STATUS:
        fraga(f"Flytt till {inp.get('till_status')} kräver Mattias uttryckliga bekräftelse för just "
              f"detta objekt ({inp.get('filnamn')}).")
    if namn in {"register_uppdatera", "register_ny_rad"}:
        falt = inp.get("falt") or {}
        if isinstance(falt, str):
            try:
                falt = json.loads(falt)
            except Exception:
                falt = {}
        if falt.get("status") in MANSKLIG_STATUS or MANSKLIGA_FALT & set(falt):
            fraga(f"Ändringen av {inp.get('objekt_id')} gäller godkännande eller publicering och "
                  "kräver Mattias bekräftelse.")
    sys.exit(0)


# 2. Webben är stängd i fas 1 --------------------------------------------------
if verktyg in {"WebFetch", "WebSearch"}:
    stoppa("Webbåtkomst används inte i fas 1. Fakta hämtas bara från 00_Underlag.")


# 3. Lokala filer --------------------------------------------------------------
def inom(sokvag, mapp):
    return sokvag == mapp or sokvag.startswith(mapp + os.sep)


def kontrollera_lokal_skrivning(sokvag):
    absolut = os.path.realpath(os.path.join(projekt, os.path.expanduser(sokvag)))
    if os.path.basename(absolut).startswith(".env") and not absolut.endswith(".env.example"):
        stoppa("Hemligheter i .env ändras aldrig av teamet.")
    if inom(absolut, os.path.join(projekt, ".git")):
        stoppa("Git-katalogen ändras aldrig direkt.")
    if utveckling:
        if not inom(absolut, projekt):
            stoppa(f"{absolut} ligger utanför projektet.")
    elif not inom(absolut, arbetsyta):
        stoppa(f"I drift skriver teamet bara i SharePoint-mappen Livv Marketing Ops och lokalt i .arbetsyta/. "
               f"Stoppat: {absolut}. Starta med LIVV_UTVECKLING=1 för att ändra projektet.")


if verktyg in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
    kontrollera_lokal_skrivning(inp.get("file_path") or inp.get("notebook_path") or "")
    sys.exit(0)

if verktyg == "Read":
    if os.path.basename(inp.get("file_path", "")).startswith(".env") and not inp.get("file_path", "").endswith(".env.example"):
        stoppa("Hemligheter i .env läses aldrig av teamet.")
    sys.exit(0)


# 4. Bash ----------------------------------------------------------------------
if verktyg == "Bash":
    kommando = inp.get("command", "") or ""
    ALLTID_STOPP = [
        (r"(^|[\s;&|(`$])(sudo\s+)?(rm|rmdir|unlink|shred|srm|trash|trash-put)(\s|$)", "Radering är spärrad."),
        (r"\bfind\b.*\s-(delete|exec|execdir|ok)\b", "find med -delete eller -exec är spärrat."),
        (r"\bgit\s+(clean|rm|reset\s+--hard|filter-branch|push\b.*(\s--force|\s-f\b|\s\+))", "Git-kommandot kan radera historik eller filer."),
        (r"(^|[\s;&|(`$])(curl|wget|ssh|scp|sftp|ftp|rsync|nc|ncat|netcat|telnet|http|https)(\s|$)", "Nätverksanrop från skalet är spärrade. Kopplingar går via MCP."),
        (r"\bgit\s+(fetch|ls-remote)\b.*(--upload-pack|\s-u\b|\s--force\b|\s-f\b|\s\+)", "git fetch och git ls-remote får inte köra egna program eller skriva över referenser."),
        (r"\bgit\b.*(--receive-pack|\bext::|\bfd::)", "git får inte köra egna program via transporten."),
        (r"(^|[\s;&|(`$])gh(\s|$).*(\bdelete\b|\s(-X|--method)[\s=]*['\"]?DELETE\b)", "Radering via gh är spärrad."),
        (r"\b(truncate|dd|mkfs)\b", "Kommandot kan skriva över eller radera data."),
        (r"\.env\b(?!\.example)", "Hemligheter i .env rörs aldrig."),
    ]
    for monster, skal in ALLTID_STOPP:
        if re.search(monster, kommando):
            stoppa(skal + f" Kommando: {kommando}")

    # gh når GitHub och får bara användas i utvecklingsläge (beslut i fas 1).
    if not utveckling and re.search(r"(^|[\s;&|(`$])gh(\s|$)", kommando):
        stoppa("gh får bara användas i utvecklingsläge. Starta med LIVV_UTVECKLING=1. "
               f"Kommando: {kommando}")

    if not utveckling:
        LASANDE = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "pwd", "date", "sort", "uniq", "cut", "diff", "file", "stat", "tree", "echo"}
        # ls-remote och fetch läser från fjärrförrådet och tillåts i drift (beslut i fas 1).
        GIT_LASANDE = {"status", "log", "diff", "show", "branch", "ls-remote", "fetch"}
        for omdirigering in re.findall(r">>?\s*([^\s;&|]+)", kommando):
            if omdirigering in ("/dev/null", "&1", "&2"):
                continue
            kontrollera_lokal_skrivning(omdirigering)
        for del_ in re.split(r"\|\||&&|[;|&\n]", kommando):
            try:
                ord_ = shlex.split(del_)
            except ValueError:
                stoppa("Kommandot kunde inte tolkas.")
            ord_ = [o for o in ord_ if not re.match(r"^\d?>>?", o)]
            if not ord_:
                continue
            forsta = os.path.basename(ord_[0])
            if forsta == "git" and len(ord_) > 1 and ord_[1] in GIT_LASANDE:
                continue
            if forsta not in LASANDE:
                stoppa(f"I drift får skalet bara köra läsande kommandon. Stoppat: {forsta}. "
                       "Starta med LIVV_UTVECKLING=1 för att ändra projektet.")
    sys.exit(0)

sys.exit(0)
