"""Teamtavlan: en lokal webbsida som visar Livvs AI-team med data från SharePoint.

Servern läser bara. Den hämtar Innehallsregister och månadens loggfiler i
09_Loggar via samma app-registrering som MCP-servern och gör inga skrivande
anrop. Sidan kan inte flytta objekt, ändra registret eller publicera.

Starta med ./tavla.sh och öppna http://127.0.0.1:8787.
Exempeldata utan SharePoint: http://127.0.0.1:8787/?exempel
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime, time as klockslag
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable

MAPP = Path(__file__).resolve().parent
sys.path.insert(0, str(MAPP.parent / "mcp"))

import sharepoint_server as sp  # noqa: E402

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
        })
    return objekt


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


def bygg_hanterare(cache: Cache):
    class Hanterare(BaseHTTPRequestHandler):
        def _svara(self, kod: int, typ: str, kropp: bytes) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(kropp)))
            self.end_headers()
            self.wfile.write(kropp)

        def do_GET(self) -> None:  # noqa: N802
            sokvag = self.path.split("?", 1)[0]
            if sokvag == "/data.json":
                try:
                    kropp = json.dumps(cache.data(), ensure_ascii=False).encode("utf-8")
                    self._svara(200, "application/json; charset=utf-8", kropp)
                except Exception as fel:  # visas på sidan, utan hemligheter
                    meddelande = str(fel) if isinstance(fel, sp.Sparrfel) else type(fel).__name__
                    kropp = json.dumps({"fel": meddelande}, ensure_ascii=False).encode("utf-8")
                    self._svara(502, "application/json; charset=utf-8", kropp)
                return
            if sokvag in STATISKA:
                fil, typ = STATISKA[sokvag]
                self._svara(200, typ, (MAPP / fil).read_bytes())
                return
            self._svara(404, "text/plain; charset=utf-8", "Finns inte".encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # ingen loggning av anrop i terminalen

    return Hanterare


def main() -> None:
    port = int(os.environ.get("TAVLA_PORT", "8787"))
    graph = LasGraph()
    cache = Cache(lambda: hamta(graph))
    server = ThreadingHTTPServer((VARD, port), bygg_hanterare(cache))
    print(f"Teamtavlan körs på http://{VARD}:{port}  (avsluta med Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTeamtavlan stängd.")


if __name__ == "__main__":
    main()
