"""MCP-server mot xAI (Grok) för A1 Trendspotter. Ett enda verktyg: trendsok.

Till Grok skickas bara en kort sökfråga och ett tidsfönster, aldrig internt material.
Servern stoppar frågor som ser ut att innehålla interna uppgifter: objekt-ID, sökvägar
i Livv Marketing Ops, e-postadresser, telefonnummer eller långa textstycken.
Svaret är idéunderlag, inte fakta. Det sparas av A1 i 13_Insikter och används i
material först när Mattias har verifierat det och fört över det till 00_Underlag.

Nyckeln läses från miljön (XAI_API_KEY i .env). Modellen kan ändras med XAI_MODELL.
"""

from __future__ import annotations

import functools
import os
import re
import sys
import traceback
from datetime import date, timedelta
from typing import Any

XAI_API = "https://api.x.ai/v1/responses"
STANDARDMODELL = "grok-4-1-fast"
MAX_FRAGA = 300
MAX_DAGAR = 30

SYSTEM = (
    "You are a trend scout for a Nordic hospitality partner that supplies hotels and spas "
    "with guest comfort products, amenities and textiles. Search the web and X for what is "
    "happening right now. Return 3 to 7 distinct trends. For each trend give: a short name, "
    "what is happening, why it matters for hotels and spas, and the evidence as a list of "
    "sources with URL and publication date. Only include trends you can support with sources "
    "from the requested time window. Say clearly when evidence is thin. Do not invent figures, "
    "quotes or sources."
)


class Fragefel(Exception):
    """En fråga som inte får skickas till Grok. Inget har skickats."""


# Mönster som tyder på internt material. Då skickas ingenting.
_INTERNT = [
    (re.compile(r"\b(LIVV|UNIQ)-\d{4}-\d{4}\b", re.I), "ett objekt-ID"),
    (re.compile(r"\b(0\d|1[0-3])_[A-Za-zÅÄÖåäö]+"), "en mapp i Livv Marketing Ops"),
    (re.compile(r"\b(Innehallsregister|Matregister|Livv Marketing Ops)\b", re.I), "ett internt register eller en intern mapp"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "en e-postadress"),
    (re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,}"), "ett telefonnummer eller ett långt nummer"),
    (re.compile(r"\.(md|docx|xlsx|csv|pdf)\b", re.I), "ett filnamn"),
]


def kontrollera_fraga(fraga: Any, dagar: Any) -> tuple[str, int]:
    if not isinstance(fraga, str):
        raise Fragefel("Sökfrågan måste vara text.")
    fraga = " ".join(fraga.split())
    if len(fraga) < 3:
        raise Fragefel("Sökfrågan är tom.")
    if len(fraga) > MAX_FRAGA:
        raise Fragefel(f"Sökfrågan är {len(fraga)} tecken. Högst {MAX_FRAGA}: skicka en kort fråga, aldrig ett textstycke.")
    for monster, vad in _INTERNT:
        if monster.search(fraga):
            raise Fragefel(f"Sökfrågan innehåller {vad}. Till Grok skickas bara sökfrågor, aldrig internt material. Inget skickades.")
    try:
        dagar = int(dagar)
    except (TypeError, ValueError):
        raise Fragefel("dagar måste vara ett heltal.") from None
    if not 1 <= dagar <= MAX_DAGAR:
        raise Fragefel(f"dagar ska vara mellan 1 och {MAX_DAGAR}.")
    return fraga, dagar


def anrop(fraga: str, dagar: int, idag: date, modell: str) -> dict[str, Any]:
    """Kroppen som skickas till xAI. Bara frågan, tidsfönstret och sökverktygen."""
    fran = idag - timedelta(days=dagar)
    return {
        "model": modell,
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Time window: {fran.isoformat()} to {idag.isoformat()}. Topic: {fraga}"},
        ],
        "tools": [
            {"type": "web_search"},
            {"type": "x_search", "from_date": fran.isoformat(), "to_date": idag.isoformat()},
        ],
    }


def tolka_svar(data: dict[str, Any]) -> tuple[str, list[str]]:
    """Texten och källorna ur svaret. Klarar både output_text och listan output."""
    texter: list[str] = []
    kallor: list[str] = []
    if isinstance(data.get("output_text"), str):
        texter.append(data["output_text"])
    for post in data.get("output") or []:
        if not isinstance(post, dict):
            continue
        for del_ in post.get("content") or []:
            if not isinstance(del_, dict):
                continue
            if del_.get("type") in ("output_text", "text") and isinstance(del_.get("text"), str) and not data.get("output_text"):
                texter.append(del_["text"])
            for ann in del_.get("annotations") or []:
                if isinstance(ann, dict) and ann.get("url"):
                    kallor.append(str(ann["url"]))
    for k in data.get("citations") or []:
        kallor.append(str(k.get("url") if isinstance(k, dict) else k))
    unika = list(dict.fromkeys(k for k in kallor if k))
    return "\n\n".join(t.strip() for t in texter if t.strip()), unika


class Grok:
    def __init__(self, http: Any = None, nyckel: str | None = None, modell: str | None = None) -> None:
        self.nyckel = nyckel if nyckel is not None else os.environ.get("XAI_API_KEY", "")
        self.modell = modell or os.environ.get("XAI_MODELL") or STANDARDMODELL
        if http is None:
            import httpx

            http = httpx.Client(timeout=180)
        self.http = http

    def trendsok(self, fraga: str, dagar: int = 7, idag: date | None = None) -> str:
        fraga, dagar = kontrollera_fraga(fraga, dagar)
        if not self.nyckel:
            raise Fragefel("XAI_API_KEY saknas i .env. Mattias lägger in nyckeln. Inget skickades.")
        idag = idag or date.today()
        svar = self.http.post(XAI_API, json=anrop(fraga, dagar, idag, self.modell),
                              headers={"Authorization": f"Bearer {self.nyckel}", "Content-Type": "application/json"})
        if svar.status_code >= 300:
            forklaring = {401: "nyckeln godtogs inte", 403: "nyckeln saknar behörighet",
                          404: f"modellen {self.modell} eller adressen finns inte", 429: "för många anrop eller slut på kredit"}
            try:
                detalj = str(svar.json().get("error", ""))[:300]
            except Exception:
                detalj = (getattr(svar, "text", "") or "")[:300]
            raise Fragefel(f"xAI svarade {svar.status_code}: {forklaring.get(svar.status_code, 'oväntat svar')}. {detalj}".strip())
        text, kallor = tolka_svar(svar.json())
        if not text:
            raise Fragefel("xAI svarade utan text. Försök igen med en annan fråga.")
        rader = [f"Sökfråga: {fraga}", f"Tidsfönster: {(idag - timedelta(days=dagar)).isoformat()} till {idag.isoformat()}",
                 f"Modell: {self.modell}", "Status: idéunderlag, inte verifierat", "", text, "", "Källor:"]
        rader += [f"- {k}" for k in kallor] or ["- Inga källor i svaret. Behandla allt som overifierat."]
        return "\n".join(rader)


def bygg_server(grok_fabrik=None):
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    server = MCPServer("xai", instructions="Trendsök med Grok för A1. Skicka bara korta sökfrågor, aldrig internt material.")
    _grok: dict[str, Grok] = {}

    def grok() -> Grok:
        if "x" not in _grok:
            _grok["x"] = (grok_fabrik or Grok)()
        return _grok["x"]

    def verktyg(description: str):
        def dekor(fn):
            @functools.wraps(fn)
            def omslag(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except ToolError:
                    raise
                except Fragefel as fel:
                    raise ToolError(str(fel)) from fel
                except Exception as fel:
                    traceback.print_exc(file=sys.stderr)
                    raise ToolError(f"{type(fel).__name__}: {fel}") from fel
            return server.tool(description=description)(omslag)
        return dekor

    @verktyg("Sök efter aktuella trender på webben och X med Grok. Ange en kort sökfråga på engelska, "
             "högst 300 tecken, och antal dagar bakåt (1 till 30). Skicka aldrig internt material. "
             "Svaret är idéunderlag med källor, inte fakta.")
    def trendsok(fraga: str, dagar: int = 7) -> str:
        return grok().trendsok(fraga, dagar)

    return server


if __name__ == "__main__":
    bygg_server().run("stdio")
