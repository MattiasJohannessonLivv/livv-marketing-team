"""Mattias beslut från teamtavlan: läsa ett objekt, godkänna det eller skicka tillbaka det.

Det här är det enda tavlan skriver. Besluten görs i samma ordning som A0 gör dem
enligt CLAUDE.md: kontrollera kravet, flytta filen, uppdatera raden, logga.
Loggen visar att det var Mattias som beslutade och att det skedde i tavlan.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp"))

import sharepoint_server as sp  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publicera as pub  # noqa: E402

JA = {"ja", "yes", "true", "1"}


def _httpx_klient():
    import httpx

    return httpx.Client(timeout=60)
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
        return {"namn": vald, "text": "", "fel": "The brief could not be read."}


class Beslut:
    def __init__(self, las: Any, skrivgraph: Any = None, nu: Callable[[], datetime] | None = None,
                 env: dict | None = None, http_fabrik: Callable[[], Any] | None = None,
                 linkedin_nyckel: Any = pub.las_linkedin_nyckel,
                 bekrafta: Callable[..., bool] = pub.macos_bekraftelse,
                 efter_godkannande: Callable[[str], str] | None = None) -> None:
        self.las = las
        self._skrivgraph = skrivgraph
        self._nu = nu or (lambda: datetime.now(sp.TIDSZON))
        self._env = env if env is not None else os.environ
        self._http_fabrik = http_fabrik or _httpx_klient
        self._linkedin_nyckel = linkedin_nyckel
        self._bekrafta = bekrafta
        # Startar A0 så att bildbriefen skrivs direkt (a0.py). Sätts av tavlans server, inte i testerna.
        self._efter_godkannande = efter_godkannande
        self._publicerar = threading.Lock()  # en publicering i taget, så att två klick aldrig båda går ut

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
                utkast["fel"] = f"The draft could not be read from {mapp}/{filnamn}."
        else:
            utkast["fel"] = "The register has no folder or file name for the draft."
        return {
            "id": objekt_id,
            "titel": _text(r.get("titel")) or _text(r.get("kampanj")) or objekt_id,
            "status": _text(r.get("status")),
            "kanal": _text(r.get("kanal")),
            "sida": sp.foretagssida(r)[0],
            "a3": _text(r.get("a3_utfall")),
            "sakerhet": _text(r.get("sakerhet")),
            "granskad": _text(r.get("granskad_a3_datum"))[:10],
            "varv": _text(r.get("revideringsvarv")),
            "eskalera": _text(r.get("eskalera")).lower() in JA,
            "orsak": _text(r.get("eskalera_skal")),
            "utkast": utkast,
            "brief": hitta_brief(self.las, r),
            "bilder": self.bilder(objekt_id),
            "inlaggstext": pub.inlaggstext(utkast.get("text", "")) or "",
            **self._publiceringsdel(r, utkast.get("text", "")),
        }

    def _publiceringsdel(self, r: dict[str, Any], utkast_text: str) -> dict[str, Any]:
        if _text(r.get("status")) != "Godkänd":
            return {}
        logg = self._logg(_text(r.get("objekt_id")), self.las)
        return {
            "bild_vald": self._senast(logg, "Valde bild i teamtavlan"),
            "alt_text": self._senast(logg, "Alt-text godkänd"),
            "publicering": self._publiceringslage(r, logg, utkast_text),
        }

    def godkann(self, objekt_id: str) -> str:
        livv = self._livv()
        r = self._rad(objekt_id, livv.g)  # läs direkt före ändringen
        # 1. Kravet
        if _text(r.get("status")) != "Granskning" or _text(r.get("a3_utfall")) != "Godkänd":
            raise sp.Sparrfel("Only items that A3 has approved and that are in review can be approved here.")
        if _text(r.get("eskalera")).lower() in JA:
            raise sp.Sparrfel("The item is escalated. Decide on it with A0 instead.")
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
            raise sp.Sparrfel(f"The file was moved to {mapp}, but the register could not be updated ({fel}). "
                              "Ask A0 to correct the row.") from fel
        # 4. Logga
        livv.logga("Mattias", objekt_id, "Godkände i teamtavlan", f"{mapp}/{filnamn}")
        svar = f"{objekt_id} is approved and is in {mapp}."
        # 5. Bildbriefen: A0 får besked direkt. Godkännandet gäller även om A0 inte kan startas.
        if self._efter_godkannande is not None:
            try:
                svar += " " + self._efter_godkannande(objekt_id)
            except Exception:
                svar += " A0 could not be started. A0 writes the image brief the next time you start the team."
        return svar

    # ---------------- Publicering när Mattias klickar Publicera ----------------

    def _logg(self, objekt_id: str, graph: Any) -> list[list[str]]:
        """Loggrader för objektet, den här och förra månaden: [åtgärd, kommentar]."""
        from openpyxl import load_workbook
        import io

        nu = self._nu()
        forra = (nu.replace(day=1) - timedelta(days=1))
        rader = []
        for manad in (f"{forra:%Y-%m}", f"{nu:%Y-%m}"):
            sokvag = f"09_Loggar/Logg_{manad}.xlsx"
            try:  # en månad utan loggfil hoppas över
                blad = load_workbook(io.BytesIO(graph.las(sokvag)), read_only=True, data_only=True).worksheets[0]
            except Exception:
                continue
            for r in blad.iter_rows(min_row=2, values_only=True):
                r = list(r) + [None] * 7
                if _text(r[3]) == objekt_id:
                    rader.append([_text(r[4]), _text(r[6])])
        return rader

    def _senast(self, logg: list[list[str]], atgard: str) -> str:
        traffar = [kommentar for a, kommentar in logg if a == atgard]
        return traffar[-1] if traffar else ""

    @staticmethod
    def _kanal(kanal: str) -> str:
        k = kanal.strip().lower()
        return "LinkedIn" if "linkedin" in k else "X" if k in {"x", "twitter", "x (twitter)"} else kanal

    def _publiceringslage(self, r: dict[str, Any], logg: list[list[str]], utkast_text: str) -> dict[str, Any]:
        kanal = self._kanal(_text(r.get("kanal")))
        alla = pub.kanaler(self._env, self._nyckel())
        lage: dict[str, Any] = dict(alla.get(kanal, {"redo": False, "sidor": [],
                                                      "skal": f"Publishing on {kanal or 'this channel'} is not available on the board."}))
        lage["kanal"] = kanal
        sidor = lage.get("sidor", [])
        standard = self._env.get("LINKEDIN_STANDARD_SIDA", "Livv.se") if kanal == "LinkedIn" else (sidor[0] if sidor else "")
        lage["standard"] = standard if standard in sidor else (sidor[0] if sidor else "")
        hinder = []
        # Avsändaren följer kolumnen foretagssida, så att ett inlägg aldrig går ut från fel sida.
        if kanal == "LinkedIn":
            sida, _ = sp.foretagssida(r)
            if sida in sidor:
                lage["sidor"], lage["standard"] = [sida], sida
            else:
                lage["sidor"], lage["standard"] = [], sida
                if lage.get("redo"):
                    hinder.append(f"{sida} is not a connected sender on LinkedIn. Add it to LINKEDIN_SIDOR in .env, "
                                  f"or publish by hand from the {sida} page.")
        text = pub.inlaggstext(utkast_text)
        if not text:
            hinder.append("The draft has no ## Inläggstext section. Ask A4 for a new version with it, or publish by hand.")
        elif "[SAKNAS" in text:
            hinder.append("The post text contains [SAKNAS].")
        bilder = self.bilder(_text(r.get("objekt_id")))
        vald = self._senast(logg, "Valde bild i teamtavlan")
        if bilder and vald not in bilder:
            hinder.append("Choose an image first.")
        if vald in bilder and not self._senast(logg, "Alt-text godkänd"):
            hinder.append("The alt text is not approved yet. Ask A0 to suggest one.")
        if self._senast(logg, "Publicerade i teamtavlan"):
            hinder.append("The post has already been published from the board.")
        if _text(r.get("status")) != "Godkänd":
            hinder.append("Only approved items can be published.")
        lage["hinder"] = hinder
        return lage

    def _nyckel(self) -> dict | None:
        return self._linkedin_nyckel() if callable(self._linkedin_nyckel) else self._linkedin_nyckel

    def publicera(self, objekt_id: str, sida: str) -> str:
        if not self._publicerar.acquire(blocking=False):
            raise sp.Sparrfel("A publication is already waiting for confirmation in the macOS dialog.")
        try:
            return self._publicera(objekt_id, sida)
        finally:
            self._publicerar.release()

    def _publicera(self, objekt_id: str, sida: str) -> str:
        livv = self._livv()
        r = self._rad(objekt_id, livv.g)  # läs direkt före publiceringen
        mapp, filnamn, varumarke = _text(r.get("mapp")), _text(r.get("filnamn")), _text(r.get("varumarke"))
        utkast_text = sp.fil_till_text(filnamn, livv.g.las(f"{mapp}/{filnamn}"))
        logg = self._logg(objekt_id, livv.g)
        lage = self._publiceringslage(r, logg, utkast_text)
        if lage["hinder"]:
            raise sp.Sparrfel(" ".join(lage["hinder"]))
        if not lage.get("redo"):
            raise sp.Sparrfel(lage.get("skal", "The channel is not connected."))
        if sida not in lage["sidor"]:
            raise sp.Sparrfel(f"{sida} is not a connected sender for {lage['kanal']}.")
        text = pub.inlaggstext(utkast_text)
        bildnamn = self._senast(logg, "Valde bild i teamtavlan")
        bild = self.bild(objekt_id, bildnamn) if bildnamn else None
        alt = self._senast(logg, "Alt-text godkänd")

        # Mattias bekräftar i en ruta från macOS som tavlans server visar. Ett anrop till
        # servern räcker alltså inte för att publicera: en människa vid datorn måste svara.
        if not self._bekrafta(objekt_id=objekt_id, kanal=lage["kanal"], sida=sida, text=text, bildnamn=bildnamn):
            raise sp.Sparrfel("The publication was not confirmed in the macOS dialog. Nothing was published.")
        http = self._http_fabrik()

        # Publicera
        if lage["kanal"] == "LinkedIn":
            urn = pub.linkedin_sidor(self._env)[sida]
            post_id, url = pub.LinkedIn(http, self._nyckel()["access_token"]).publicera(urn, text, bild, alt)
        else:
            post_id, url = pub.X(http, self._env).publicera(text, bild, bildnamn, alt)

        # Logga direkt, så att en andra klick aldrig publicerar igen
        livv.logga("Mattias", objekt_id, "Publicerade i teamtavlan", url, f"{lage['kanal']} som {sida}")
        try:
            livv.flytta_objekt(filnamn, varumarke, "Godkänd", "Publicerad")
            livv.register_uppdatera(objekt_id, {
                "status": "Publicerad", "mapp": sp.mapp_for_status("Publicerad", varumarke),
                "publicerad_datum": self._nu().strftime("%Y-%m-%d"), "plattforms_id": post_id, "url": url,
            })
        except Exception as fel:
            raise sp.Sparrfel(f"The post IS published: {url}. But the move or the register update did not finish ({fel}). "
                              "Ask A0 to correct the row. Do not publish again.") from fel
        return f"{objekt_id} is published on {lage['kanal']} as {sida}: {url}"

    # ---------------- Logotypen i 00_Underlag ----------------

    def logotyp(self) -> tuple[bytes, str]:
        """Livvs logotyp från 00_Underlag, så att den aldrig behöver ligga i Git."""
        typer = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        namn = sorted(n for n in self.las.lista("00_Underlag")
                      if n.lower().startswith("livv_signatur") and Path(n).suffix.lower() in typer)
        if not namn:
            raise sp.Sparrfel("Hittar ingen logotyp (livv_signatur) i 00_Underlag.")
        return self.las.las(f"00_Underlag/{namn[0]}"), typer[Path(namn[0]).suffix.lower()]

    # ---------------- Livvs typsnitt Crake från 00_Underlag ----------------

    FONTTYPER = {".woff2": "font/woff2", ".woff": "font/woff", ".otf": "font/otf", ".ttf": "font/ttf"}

    def _fontfiler(self) -> list[str]:
        """Crake-filer i 00_Underlag eller 00_Underlag/Fonter. Licensierade, så de ligger aldrig i Git."""
        filer = []
        for mapp in ("00_Underlag", "00_Underlag/Fonter"):
            try:
                namn = self.las.lista(mapp)
            except Exception:
                continue
            filer += [f"{mapp}/{n}" for n in namn
                      if n.lower().startswith("crake") and Path(n).suffix.lower() in self.FONTTYPER]
        return sorted(filer)

    @staticmethod
    def _vikt(namn: str) -> int:
        n = namn.lower().replace("-", "").replace(" ", "")
        for ord_, vikt in (("extralight", 200), ("light", 300), ("semibold", 600), ("medium", 500), ("bold", 700)):
            if ord_ in n:
                return vikt
        return 400

    def fonter_css(self) -> str:
        regler = []
        for sokvag in self._fontfiler():
            namn = sokvag.rsplit("/", 1)[1]
            stil = "italic" if "italic" in namn.lower() else "normal"
            url = "font?namn=" + quote(namn)
            regler.append(f'@font-face {{ font-family: "Crake Livv"; src: url("{url}"); '
                          f"font-weight: {self._vikt(namn)}; font-style: {stil}; font-display: swap; }}")
        return "\n".join(regler) + "\n"

    def font(self, namn: str) -> tuple[bytes, str]:
        for sokvag in self._fontfiler():
            if sokvag.rsplit("/", 1)[1] == namn:
                return self.las.las(sokvag), self.FONTTYPER[Path(namn).suffix.lower()]
        raise sp.Sparrfel("Typsnittet finns inte i 00_Underlag.")

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
            raise sp.Sparrfel("An image can be chosen once the text is approved.")
        if namn not in self.bilder(objekt_id):
            raise sp.Sparrfel("Bilden finns inte bland förslagen.")
        if self._senast(self._logg(objekt_id, livv.g), "Valde bild i teamtavlan") == namn:
            return f"The image {namn} is already chosen for {objekt_id}. Nothing new was logged."
        livv.logga("Mattias", objekt_id, "Valde bild i teamtavlan", f"{sp.BILDMAPP}/{objekt_id}/{namn}", namn)
        return f"The image {namn} is chosen for {objekt_id}."

    def tillbaka(self, objekt_id: str, kommentar: str) -> str:
        kommentar = " ".join(_text(kommentar).split())[:MAX_KOMMENTAR]
        if not kommentar:
            raise sp.Sparrfel("Write what should change.")
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
            raise sp.Sparrfel("Only items waiting for your decision can be sent back from here.")
        livv.register_uppdatera(objekt_id, falt)
        livv.logga("Mattias", objekt_id, "Begärde ändring i teamtavlan", sp.mapp_for_status("Utkast", varumarke), kommentar)
        return f"{objekt_id} is back with A4. A0 gives your comment to A4 the next time the team works."
