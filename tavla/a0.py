"""Startar A0 i bakgrunden när Mattias har godkänt ett objekt i teamtavlan.

A0 får ett enda uppdrag: skriva bildbriefen för objektet enligt 5b i CLAUDE.md.
Körningen startas alltid i driftläge och får bara verktygen för att läsa, spara
bildbriefen och logga. Spärren i .claude/hooks/ gäller som vanligt, och allt som
kräver Mattias bekräftelse stoppas eftersom ingen människa sitter vid körningen.

Ingen chatt är öppen, så A0 svarar inte Mattias. Beskedet är pingen i Teams
och raden "Bildbrief sparad" i loggen. Går körningen fel skriver A0 bildbriefen
nästa gång teamet startas (CLAUDE.md, steg 5). Utskriften från körningen sparas
i .arbetsyta/a0-bildbrief/.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROT = Path(__file__).resolve().parent.parent
LOGGMAPP = ROT / ".arbetsyta" / "a0-bildbrief"
OBJEKT_ID_RE = re.compile(r"^(LIVV|UNIQ)-\d{4}-\d{4}$")

# Det enda A0 får göra i körningen
TILLATNA_VERKTYG = [
    "mcp__sharepoint__lista_mapp",
    "mcp__sharepoint__las_fil",
    "mcp__sharepoint__register_las",
    "mcp__sharepoint__spara_bildbrief",
    "mcp__sharepoint__logga",
]
SPARRADE_VERKTYG = [
    "Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent",
    "mcp__sharepoint__skapa_brief", "mcp__sharepoint__spara_utkast", "mcp__sharepoint__spara_rapport",
    "mcp__sharepoint__flytta_objekt", "mcp__sharepoint__register_ny_rad", "mcp__sharepoint__register_uppdatera",
    "mcp__sharepoint__visa_bild",
]


def uppdrag(objekt_id: str) -> str:
    return (
        f"Mattias godkände {objekt_id} i teamtavlan just nu. Ditt enda uppdrag är steg 5b i CLAUDE.md "
        f"för {objekt_id}. Lista först 12_Pictures/{objekt_id}. Finns redan en fil med image-brief i namnet: "
        "gör ingenting mer. Annars: läs raden i registret, det godkända utkastet, briefen och bildstilen "
        "Bildstil_Please_Disturb i 00_Underlag, skriv bildbriefen på engelska med exakt de delar som står i 5b "
        "och spara den med spara_bildbrief. Logga med agent A0, åtgärden \"Bildbrief sparad\" och sökvägen. "
        "Innehåller det godkända utkastet text för bilden: skriv i loggens kommentar att bilden inte får ha text "
        "och vilken text det gällde. Ingen chatt är öppen, så allt Mattias behöver veta ska stå i loggen. "
        "Gör inget annat: inga statusbyten, inga ändringar i registret, inga andra filer."
    )


def kommando(claude: str, objekt_id: str) -> list[str]:
    return [
        claude, "-p", uppdrag(objekt_id),
        "--allowedTools", ",".join(TILLATNA_VERKTYG),
        "--disallowedTools", ",".join(SPARRADE_VERKTYG),
    ]


class Bildbriefstartare:
    """Startar en A0-körning per objekt. Ett objekt har aldrig två körningar samtidigt."""

    def __init__(self, starta: Callable[..., Any] = subprocess.Popen,
                 hitta: Callable[[str], str | None] = shutil.which,
                 miljo: dict[str, str] | None = None, loggmapp: Path = LOGGMAPP) -> None:
        self._starta = starta
        self._hitta = hitta
        self._miljo = miljo
        self._loggmapp = loggmapp
        self._las = threading.Lock()
        self._pagar: dict[str, Any] = {}

    def __call__(self, objekt_id: str) -> str:
        """Startar körningen och returnerar ett besked till Mattias. Kastar aldrig fel."""
        if not OBJEKT_ID_RE.match(objekt_id or ""):
            return "A0 startades inte: ogiltigt objekt-ID."
        claude = self._hitta("claude")
        if not claude:
            return ("A0 kunde inte startas eftersom Claude Code inte hittades på datorn. "
                    "A0 skriver bildbriefen nästa gång du startar teamet.")
        with self._las:
            tidigare = self._pagar.get(objekt_id)
            if tidigare is not None and tidigare.poll() is None:
                return "A0 skriver redan bildbriefen."
            miljo = dict(os.environ if self._miljo is None else self._miljo)
            miljo["LIVV_UTVECKLING"] = "0"  # alltid driftläge, oavsett hur tavlan startades
            try:
                self._loggmapp.mkdir(parents=True, exist_ok=True)
                utskrift = open(self._loggmapp / f"{objekt_id}_{datetime.now():%Y%m%d-%H%M%S}.log", "w", encoding="utf-8")
                with utskrift:
                    self._pagar[objekt_id] = self._starta(
                        kommando(claude, objekt_id), cwd=str(ROT), env=miljo,
                        stdin=subprocess.DEVNULL, stdout=utskrift, stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
            except Exception as fel:
                return (f"A0 kunde inte startas ({type(fel).__name__}: {fel}). "
                        "A0 skriver bildbriefen nästa gång du startar teamet.")
        return ("A0 skriver bildbriefen nu. När den är sparad får Brand Studio en ping i Teams, "
                "och Bildbrief sparad syns i loggen.")
