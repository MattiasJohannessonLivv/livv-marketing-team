"""Teamtavlan: en lokal webbsida som visar Livvs AI-team med data från SharePoint.

Servern hämtar Innehallsregister och loggfilerna i 09_Loggar via samma
app-registrering som MCP-servern. Den skriver bara när Mattias själv godkänner
ett objekt eller skickar tillbaka det i tavlan (se beslut.py). Sidan kan aldrig
publicera, schemalägga eller ändra något annat.

Medan tavlan körs kontrollerar den registret var femte minut och skickar en
notis på Macen när något nytt väntar på Mattias. Stäng av med TAVLA_NOTISER=0.

Starta med ./tavla.sh och öppna http://127.0.0.1:8787.
Exempeldata utan SharePoint: http://127.0.0.1:8787/?exempel
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import date, datetime, time as klockslag
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs

MAPP = Path(__file__).resolve().parent
sys.path.insert(0, str(MAPP.parent / "mcp"))
sys.path.insert(0, str(MAPP))

import sharepoint_server as sp  # noqa: E402
from beslut import Beslut  # noqa: E402

VARD = "127.0.0.1"  # bara den egna datorn, aldrig nätverket
CACHE_SEKUNDER = 300
STATISKA = {
    "/": ("tavla.html", "text/html; charset=utf-8"),
    "/tavla.html": ("tavla.html", "text/html; charset=utf-8"),
    "/exempeldata.json": ("exempeldata.json", "application/json; charset=utf-8"),
}


class LasGraph:
    """Bara läsning. Exponerar varken skriv, flytta eller skapa mapp."""

    def __init__(self, graph: Any = None) -> None:
        self._g = graph if graph is not None else sp.Graph()

    def las(self, sokvag: str) -> bytes:
        return self._g.las(sokvag)

    def finns(self, sokvag: str) -> bool:
        return self._g.finns(sokvag)

    def webblank(self, sokvag: str) -> str:
        return self._g.objekt(sokvag).get("webUrl", "")

    def lista(self, sokvag: str) -> list[str]:
        return [p["name"] for p in self._g.lista(sokvag)]


# ---------------------------------------------------------------------------
# Omvandling från Excel till det format sidan använder
# ---------------------------------------------------------------------------

def _text(v: Any) -> str:
    return "" if v is None else str(v).strip()


_DATUM_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_KLOCKA_RE = re.compile(r"(\d{1,2})[:.](\d{2})")


def _datum(v: Any) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    m = _DATUM_RE.search(_text(v))
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else ""


def _tidpunkt(v: Any) -> str:
    """YYYY-MM-DDTHH:MM, eller tom sträng."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M")
    if isinstance(v, date):
        return v.isoformat() + "T00:00"
    datum = _datum(v)
    if not datum:
        return ""
    resten = _DATUM_RE.sub("", _text(v), count=1)
    return f"{datum}T{_klocka(resten) or '00:00'}"


def _klocka(v: Any) -> str:
    """HH:MM. Klarar 09:52, 9:52, 9.52, 09:52:00 och Excels del av dygn."""
    if isinstance(v, (datetime, klockslag)):
        return v.strftime("%H:%M")
    if isinstance(v, float) and 0 <= v < 1:
        minuter = round(v * 1440)
        return f"{minuter // 60:02d}:{minuter % 60:02d}"
    m = _KLOCKA_RE.search(_text(v))
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return ""
    return f"{int(m[1]):02d}:{m[2]}"


def _heltal(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def objekt_fran_register(rader: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    objekt = []
    for r in rader:
        objekt_id = _text(r.get("objekt_id"))
        if not objekt_id:
            continue
        objekt.append({
            "id": objekt_id,
            "bolag": sp.VARUMARKESMAPPAR.get(_text(r.get("varumarke")), "Okand"),
            "kanal": _text(r.get("kanal")),
            "titel": _text(r.get("titel")) or _text(r.get("kampanj")) or objekt_id,
            "status": _text(r.get("status")),
            "a3": _text(r.get("a3_utfall")),
            "varv": _heltal(r.get("revideringsvarv")),
            "plan": _datum(r.get("planerad_publicering")),
            "sedan": _tidpunkt(r.get("senast_andrad")),
            "orsak": _text(r.get("eskalera_skal")),
            "eskalera": _text(r.get("eskalera")).lower() in {"ja", "yes", "true", "1"},
            "briefdatum": _tidpunkt(r.get("briefdatum")),
            "godkand_datum": _tidpunkt(r.get("godkand_datum")),
            "mapp": _text(r.get("mapp")),
            "filnamn": _text(r.get("filnamn")),
        })
    return objekt


def vantande(objekt: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Objekt som väntar på Mattias. Samma regler som listan Väntar på dig på sidan."""
    lista = []
    for o in objekt:
        if o["status"] in {"Avvisad", "Arkiverad", "Publicerad"}:
            continue
        if o["eskalera"]:
            etikett = "Beslut"
        elif o["status"] == "Granskning" and o["a3"] == "Godkänd":
            etikett = "Godkänn"
        elif o["status"] == "Godkänd":
            etikett = "Publicera"
        elif o["status"] == "Schemalagd":
            etikett = "Bekräfta"
        else:
            continue
        lista.append({**o, "etikett": etikett})
    return lista


def logg_fran_bok(data: bytes) -> list[list[str]]:
    """Rader som [datum, tid, agent, objekt-ID, åtgärd, kommentar]."""
    from openpyxl import load_workbook

    sp.logg_kontrollera_kolumner(data)
    blad = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    rader = []
    for r in blad.iter_rows(min_row=2, values_only=True):
        r = list(r) + [None] * 7
        datum = _datum(r[0])
        if not datum:
            continue
        rader.append([datum, _klocka(r[1]), _text(r[2]), _text(r[3]), _text(r[4]), _text(r[6])])
    return rader


def manader(nu: datetime) -> list[str]:
    """Den här och förra månaden, så att de senaste 14 dagarna alltid täcks."""
    sista_i_forra = date.fromordinal(nu.date().replace(day=1).toordinal() - 1)
    return [f"{sista_i_forra:%Y-%m}", f"{nu:%Y-%m}"]


def hamta(graph: Any, nu: datetime | None = None) -> dict[str, Any]:
    nu = nu or datetime.now(sp.TIDSZON)
    objekt = objekt_fran_register(sp.register_rader(graph.las(sp.REGISTER_FIL)))
    logg: list[list[str]] = []
    varningar: list[str] = []
    for manad in manader(nu):
        sokvag = f"09_Loggar/Logg_{manad}.xlsx"
        if not graph.finns(sokvag):
            continue
        try:
            logg += logg_fran_bok(graph.las(sokvag))
        except sp.Sparrfel as fel:
            varningar.append(f"{sokvag}: {fel}")
    logg.sort(key=lambda rad: (rad[0], rad[1]))
    # Direktlänk till filen för det som väntar på Mattias, så att han kommer rätt i SharePoint
    for o in vantande(objekt):
        if o["mapp"] and o["filnamn"]:
            try:
                lank = graph.webblank(f"{o['mapp']}/{o['filnamn']}")
            except Exception:  # länken är en bekvämlighet, tavlan fungerar utan den
                lank = ""
            next(x for x in objekt if x["id"] == o["id"])["lank"] = lank
    return {
        "kalla": "sharepoint",
        "hamtad": nu.strftime("%Y-%m-%dT%H:%M"),
        "objekt": objekt,
        "logg": logg,
        "varningar": varningar,
    }


# ---------------------------------------------------------------------------
# Webbserver
# ---------------------------------------------------------------------------

class Cache:
    def __init__(self, hamtare, sekunder: int = CACHE_SEKUNDER) -> None:
        self._hamtare = hamtare
        self._sekunder = sekunder
        self._las = threading.Lock()
        self._data: dict[str, Any] | None = None
        self._tid = 0.0

    def data(self) -> dict[str, Any]:
        with self._las:
            if self._data is None or time.monotonic() - self._tid > self._sekunder:
                self._data = self._hamtare()
                self._tid = time.monotonic()
            return self._data

    def rensa(self) -> None:
        with self._las:
            self._data = None


NYCKEL_PLATS = "__TAVLA_NYCKEL__"


def bygg_hanterare(cache: Cache, beslut: Any = None, nyckel: str | None = None):
    """Webbservern. Läser för alla sidor. Skriver bara via Mattias beslut i tavlan (POST),
    och bara med nyckeln som finns i sidan som servern själv levererade."""
    nyckel = nyckel or secrets.token_urlsafe(32)

    class Hanterare(BaseHTTPRequestHandler):
        def _svara(self, kod: int, typ: str, kropp: bytes) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(kropp)))
            self.end_headers()
            self.wfile.write(kropp)

        def _json(self, kod: int, data: dict[str, Any]) -> None:
            self._svara(kod, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False).encode("utf-8"))

        def _ratt_vard(self) -> bool:
            """Skydd mot DNS rebinding: bara anrop till den egna datorn under rätt namn."""
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _fel(self, fel: Exception) -> None:
            meddelande = str(fel) if isinstance(fel, sp.Sparrfel) else type(fel).__name__
            self._json(502, {"fel": meddelande})

        def do_GET(self) -> None:  # noqa: N802
            if not self._ratt_vard():
                self._svara(403, "text/plain; charset=utf-8", "Fel värd".encode("utf-8"))
                return
            sokvag, _, fraga = self.path.partition("?")
            if sokvag == "/data.json":
                try:
                    self._json(200, cache.data())
                except Exception as fel:  # visas på sidan, utan hemligheter
                    self._fel(fel)
                return
            if sokvag == "/objekt" and beslut is not None:
                objekt_id = parse_qs(fraga).get("id", [""])[0]
                try:
                    self._json(200, beslut.detalj(objekt_id))
                except Exception as fel:
                    self._fel(fel)
                return
            if sokvag in STATISKA:
                fil, typ = STATISKA[sokvag]
                kropp = (MAPP / fil).read_bytes()
                if fil == "tavla.html":
                    kropp = kropp.replace(NYCKEL_PLATS.encode(), nyckel.encode())
                self._svara(200, typ, kropp)
                return
            self._svara(404, "text/plain; charset=utf-8", "Finns inte".encode("utf-8"))

        def do_POST(self) -> None:  # noqa: N802
            sokvag = self.path.split("?", 1)[0]
            if sokvag not in {"/godkann", "/tillbaka"} or beslut is None:
                self._svara(404, "text/plain; charset=utf-8", "Finns inte".encode("utf-8"))
                return
            port = self.server.server_address[1]
            ursprung = self.headers.get("Origin")
            if (not self._ratt_vard()
                    or (ursprung and ursprung not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"})
                    or not self.headers.get("Content-Type", "").startswith("application/json")
                    or not secrets.compare_digest(self.headers.get("X-Tavla-Nyckel", ""), nyckel)):
                self._json(403, {"fel": "Beslut kan bara göras från teamtavlan på den här datorn."})
                return
            try:
                langd = min(int(self.headers.get("Content-Length", "0")), 10_000)
                data = json.loads(self.rfile.read(langd) or b"{}")
                objekt_id = str(data.get("id", ""))
                if sokvag == "/godkann":
                    text = beslut.godkann(objekt_id)
                else:
                    text = beslut.tillbaka(objekt_id, str(data.get("kommentar", "")))
                cache.rensa()
                self._json(200, {"ok": True, "text": text})
            except Exception as fel:
                self._fel(fel)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # ingen loggning av anrop i terminalen

    return Hanterare


# ---------------------------------------------------------------------------
# Notiser på Macen när något nytt väntar på Mattias
# ---------------------------------------------------------------------------

def notis_skript(titel: str, text: str) -> str:
    """AppleScript för en notis. json.dumps ger en citerad sträng som AppleScript förstår."""
    def citera(t: str) -> str:
        return json.dumps(" ".join(t.split()), ensure_ascii=False)
    return f'display notification {citera(text)} with title {citera(titel)} sound name "Glass"'


def macnotis(titel: str, text: str) -> None:
    if shutil.which("osascript"):
        subprocess.run(["osascript", "-e", notis_skript(titel, text)], check=False, timeout=10)


class Pingare:
    """Skickar en notis för varje nytt objekt som väntar på Mattias, och en sammanfattning vid start."""

    def __init__(self, skicka=macnotis) -> None:
        self._skicka = skicka
        self._sett: set[tuple[str, str]] | None = None

    def kontrollera(self, data: dict[str, Any]) -> None:
        lista = vantande(data.get("objekt", []))
        nycklar = {(o["id"], o["etikett"]) for o in lista}
        if self._sett is None:
            if lista:
                antal = len(lista)
                self._skicka("Livv Marketing Ops", f"{antal} {'sak väntar' if antal == 1 else 'saker väntar'} på ditt beslut.")
        else:
            for o in lista:
                if (o["id"], o["etikett"]) not in self._sett:
                    self._skicka(f"Livv: {o['etikett']}", f"{o['id']} {o['titel']}")
        self._sett = nycklar


def bevaka(cache: Cache, pingare: Pingare) -> None:
    while True:
        try:
            pingare.kontrollera(cache.data())
        except Exception:  # felet visas på sidan, bevakningen fortsätter
            pass
        time.sleep(CACHE_SEKUNDER + 5)


def main() -> None:
    port = int(os.environ.get("TAVLA_PORT", "8787"))
    graph = LasGraph()
    cache = Cache(lambda: hamta(graph))
    server = ThreadingHTTPServer((VARD, port), bygg_hanterare(cache, Beslut(graph)))
    print(f"Teamtavlan körs på http://{VARD}:{port}  (avsluta med Ctrl+C)")
    if os.environ.get("TAVLA_NOTISER", "1") != "0":
        threading.Thread(target=bevaka, args=(cache, Pingare()), daemon=True).start()
        print("Notiser är på: du får en notis när något nytt väntar på dig.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTeamtavlan stängd.")


if __name__ == "__main__":
    main()
