"""Mattias beslut från teamtavlan: läsa ett objekt, godkänna det eller skicka tillbaka det.

Det här är det enda tavlan skriver. Besluten görs i samma ordning som A0 gör dem
enligt CLAUDE.md: kontrollera kravet, flytta filen, uppdatera raden, logga.
Loggen visar att det var Mattias som beslutade och att det skedde i tavlan.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp"))

import sharepoint_server as sp  # noqa: E402

JA = {"ja", "yes", "true", "1"}
MAX_KOMMENTAR = 1000


def _text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def hitta_brief(las: Any, rad: dict[str, Any]) -> dict[str, str] | None:
    """Briefen har samma kanal och kampanj i filnamnet som utkastet och ligger kvar i 01_Briefer."""
    m = sp.FILNAMN_RE.match(_text(rad.get("filnamn")))
    if not m:
        return None
    try:
        mapp = f"01_Briefer/{sp.varumarkesmapp(_text(rad.get('varumarke')))}"
        namn = las.lista(mapp)
    except Exception:
        return None
    kandidater = []
    for n in namn:
        b = sp.FILNAMN_RE.match(n)
        if b and b["format"] == "brief" and b["kanal"] == m["kanal"] and b["kampanj"] == m["kampanj"]:
            kandidater.append(n)
    if not kandidater:
        return None
    vald = max(kandidater)
    try:
        return {"namn": vald, "text": sp.fil_till_text(vald, las.las(f"{mapp}/{vald}"))}
    except Exception:
        return {"namn": vald, "text": "", "fel": "Briefen kunde inte läsas."}


class Beslut:
    def __init__(self, las: Any, skrivgraph: Any = None, nu: Callable[[], datetime] | None = None) -> None:
        self.las = las
        self._skrivgraph = skrivgraph
        self._nu = nu or (lambda: datetime.now(sp.TIDSZON))

    def _livv(self) -> sp.Livv:
        if self._skrivgraph is None:
            self._skrivgraph = sp.Graph()
        return sp.Livv(self._skrivgraph)

    @staticmethod
    def _rad(objekt_id: str, graph: Any) -> dict[str, Any]:
        if not sp.OBJEKT_ID_RE.match(objekt_id or ""):
            raise sp.Sparrfel("Ogiltigt objekt-ID.")
        rader = sp.register_rader(graph.las(sp.REGISTER_FIL), objekt_id)
        if len(rader) != 1:
            raise sp.Sparrfel(f"{objekt_id} finns inte i registret.")
        return rader[0]

    def detalj(self, objekt_id: str) -> dict[str, Any]:
        r = self._rad(objekt_id, self.las)
        mapp, filnamn = _text(r.get("mapp")), _text(r.get("filnamn"))
        utkast: dict[str, str] = {"namn": filnamn, "text": ""}
        if mapp and filnamn:
            try:
                utkast["text"] = sp.fil_till_text(filnamn, self.las.las(f"{mapp}/{filnamn}"))
            except Exception:
                utkast["fel"] = f"Utkastet kunde inte läsas från {mapp}/{filnamn}."
        else:
            utkast["fel"] = "Registret saknar mapp eller filnamn för utkastet."
        return {
            "id": objekt_id,
            "titel": _text(r.get("titel")) or _text(r.get("kampanj")) or objekt_id,
            "status": _text(r.get("status")),
            "kanal": _text(r.get("kanal")),
            "a3": _text(r.get("a3_utfall")),
            "sakerhet": _text(r.get("sakerhet")),
            "granskad": _text(r.get("granskad_a3_datum"))[:10],
            "varv": _text(r.get("revideringsvarv")),
            "eskalera": _text(r.get("eskalera")).lower() in JA,
            "orsak": _text(r.get("eskalera_skal")),
            "utkast": utkast,
            "brief": hitta_brief(self.las, r),
            "bilder": self.bilder(objekt_id),
        }

    def godkann(self, objekt_id: str) -> str:
        livv = self._livv()
        r = self._rad(objekt_id, livv.g)  # läs direkt före ändringen
        # 1. Kravet
        if _text(r.get("status")) != "Granskning" or _text(r.get("a3_utfall")) != "Godkänd":
            raise sp.Sparrfel("Bara objekt som A3 har godkänt och som står i Granskning kan godkännas här.")
        if _text(r.get("eskalera")).lower() in JA:
            raise sp.Sparrfel("Objektet är eskalerat. Besluta om det med A0 i stället.")
        varumarke, filnamn = _text(r.get("varumarke")), _text(r.get("filnamn"))
        # 2. Flytta filen
        livv.flytta_objekt(filnamn, varumarke, "Granskning", "Godkänd")
        mapp = sp.mapp_for_status("Godkänd", varumarke)
        # 3. Uppdatera raden
        try:
            livv.register_uppdatera(objekt_id, {
                "status": "Godkänd", "mapp": mapp, "godkand_av": "Mattias",
                "godkand_datum": self._nu().strftime("%Y-%m-%d"),
            })
        except Exception as fel:
            raise sp.Sparrfel(f"Filen är flyttad till {mapp}, men registret kunde inte uppdateras ({fel}). "
                              "Be A0 rätta raden.") from fel
        # 4. Logga
        livv.logga("Mattias", objekt_id, "Godkände i teamtavlan", f"{mapp}/{filnamn}")
        return f"{objekt_id} är godkänd och ligger i {mapp}."

    # ---------------- Logotypen i 00_Underlag ----------------

    def logotyp(self) -> tuple[bytes, str]:
        """Livvs logotyp från 00_Underlag, så att den aldrig behöver ligga i Git."""
        typer = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        namn = sorted(n for n in self.las.lista("00_Underlag")
                      if n.lower().startswith("livv_signatur") and Path(n).suffix.lower() in typer)
        if not namn:
            raise sp.Sparrfel("Hittar ingen logotyp (livv_signatur) i 00_Underlag.")
        return self.las.las(f"00_Underlag/{namn[0]}"), typer[Path(namn[0]).suffix.lower()]

    # ---------------- Bilder från Brand Studio ----------------

    def bilder(self, objekt_id: str) -> list[str]:
        """Bildförslag i 12_Pictures/<objekt-ID>, i namnordning."""
        if not sp.OBJEKT_ID_RE.match(objekt_id or ""):
            return []
        try:
            namn = self.las.lista(f"{sp.BILDMAPP}/{objekt_id}")
        except Exception:
            return []
        return sorted(n for n in namn if n.lower().endswith(sp.BILDTYPER) and "/" not in n)

    def bild(self, objekt_id: str, namn: str) -> bytes:
        if namn not in self.bilder(objekt_id):
            raise sp.Sparrfel("Bilden finns inte bland förslagen.")
        return self.las.las(f"{sp.BILDMAPP}/{objekt_id}/{namn}")

    def valj_bild(self, objekt_id: str, namn: str) -> str:
        livv = self._livv()
        r = self._rad(objekt_id, livv.g)
        if _text(r.get("status")) not in sp.TEXT_GODKAND:
            raise sp.Sparrfel("Bild väljs först när texten är godkänd.")
        if namn not in self.bilder(objekt_id):
            raise sp.Sparrfel("Bilden finns inte bland förslagen.")
        livv.logga("Mattias", objekt_id, "Valde bild i teamtavlan", f"{sp.BILDMAPP}/{objekt_id}/{namn}", namn)
        return f"Bilden {namn} är vald för {objekt_id}."

    def tillbaka(self, objekt_id: str, kommentar: str) -> str:
        kommentar = " ".join(_text(kommentar).split())[:MAX_KOMMENTAR]
        if not kommentar:
            raise sp.Sparrfel("Skriv vad som ska ändras.")
        livv = self._livv()
        r = self._rad(objekt_id, livv.g)
        status, varumarke, filnamn = _text(r.get("status")), _text(r.get("varumarke")), _text(r.get("filnamn"))
        eskalerad = _text(r.get("eskalera")).lower() in JA
        if status == "Granskning":
            livv.flytta_objekt(filnamn, varumarke, "Granskning", "Utkast")
            falt = {"status": "Utkast", "mapp": sp.mapp_for_status("Utkast", varumarke), "a3_utfall": "Revidera"}
        elif status == "Utkast" and eskalerad:
            falt = {"eskalera": "Nej", "a3_utfall": "Revidera"}
        else:
            raise sp.Sparrfel("Bara objekt som väntar på ditt beslut kan skickas tillbaka härifrån.")
        livv.register_uppdatera(objekt_id, falt)
        livv.logga("Mattias", objekt_id, "Begärde ändring i teamtavlan", sp.mapp_for_status("Utkast", varumarke), kommentar)
        return f"{objekt_id} är tillbaka hos A4. A0 ger din kommentar till A4 nästa gång teamet arbetar."
