"""MCP-server för Livv Marketing Ops i SharePoint.

Servern ger teamet exakt de verktyg loopen behöver och inget mer.
Den arbetar bara med sökvägar relativt rotmappen Livv Marketing Ops.
Den saknar helt verktyg för radering, namnbyte, behörigheter och delning.
Innehållsfiler skrivs aldrig över: en ny version får ett nytt vNN.
Bara Innehallsregister och loggen skrivs om, enligt reglerna i livv-grund.

Inloggning sker med app-behörighet (client credentials) från en
app-registrering i Entra ID med Sites.Selected för webbplatsen.
Hemligheterna läses från miljövariabler, se .env.example.
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

# Platser från livv-grund. De är låsta här i koden med avsikt:
# servern kan inte pekas om till en annan drive eller mapp via miljön.
DRIVE_ID = "b!rXxF7V33YU-pcztAgMnzctUqcRF4PUtHlrOvU9obVBisHk1qgi4dRYi2wNZl121H"
ROT_ID = "01IDL2BRVMDAD4OA3NIFFZFBKDEFGJP7RS"  # Livv Marketing Ops

GRAPH = "https://graph.microsoft.com/v1.0"
TIDSZON = ZoneInfo("Europe/Stockholm")
MAX_FILSTORLEK = 4 * 1024 * 1024  # enkel uppladdning i Graph klarar upp till 4 MB

REGISTER_FIL = "Innehallsregister.xlsx"
REGISTER_BLAD = "Register"
LOGG_KOLUMNER = ["Datum", "Tid", "Agent", "Objekt-ID", "Åtgärd", "Fil eller mapp", "Kommentar"]

# Mappar som får finnas överst i Livv Marketing Ops
TILLATNA_TOPPNIVAER = {
    "00_Underlag", "01_Briefer", "02_Utkast", "03_Granskning", "04_Godkant",
    "05_Publicerat", "06_Arkiv", "07_Avvisat", "08_Rapporter", "09_Loggar",
    "10_Prompter", "11_Dataimport", "Innehallsregister.xlsx", "Matregister.xlsx",
}

VARUMARKESMAPPAR = {"Livv Group": "LivvGroup", "Livv": "Livv", "Unique": "Unique"}

# Status och mapp enligt bladet Statusflode
STATUSMAPPAR = {
    "Brief": "01_Briefer",
    "Utkast": "02_Utkast",
    "Granskning": "03_Granskning",
    "Godkänd": "04_Godkant",
    "Schemalagd": "04_Godkant",
    "Publicerad": "05_Publicerat",
    "Arkiverad": "06_Arkiv",
    "Avvisad": "07_Avvisat",
}

# Tillåtna flyttar av en fil. Allt annat avvisas av servern.
# Ingenting flyttas någonsin ut ur 06_Arkiv.
TILLATNA_FLYTTAR = {
    ("Utkast", "Granskning"),
    ("Utkast", "Avvisad"),
    ("Granskning", "Utkast"),
    ("Granskning", "Godkänd"),
    ("Granskning", "Avvisad"),
    ("Godkänd", "Schemalagd"),
    ("Godkänd", "Publicerad"),
    ("Godkänd", "Avvisad"),
    ("Schemalagd", "Publicerad"),
    ("Publicerad", "Arkiverad"),
}

FILNAMN_RE = re.compile(
    r"^(?P<datum>\d{8})_(?P<varumarke>livv|livvgroup|unique)_(?P<kanal>[a-z0-9-]+)_"
    r"(?P<kampanj>[a-z0-9-]+)_(?P<format>[a-z0-9-]+)_v(?P<version>\d{2})\.(?P<typ>md|docx)$"
)
OBJEKT_ID_RE = re.compile(r"^(LIVV|UNIQ)-\d{4}-\d{4}$")
RAPPORTNAMN_RE = re.compile(r"^[A-Za-z0-9_-]+\.(md|docx)$")


class Sparrfel(Exception):
    """Ett anrop som bryter mot reglerna. Inget har ändrats."""


# ---------------------------------------------------------------------------
# Kontroller utan nätverk. De testas i tests/test_sokvagar.py.
# ---------------------------------------------------------------------------

def kontrollera_sokvag(sokvag: str) -> str:
    """Returnerar en säker sökväg relativt rotmappen eller stoppar."""
    if not isinstance(sokvag, str):
        raise Sparrfel("Sökvägen måste vara text.")
    sokvag = sokvag.strip().strip("/")
    if sokvag == "":
        return ""
    if "\\" in sokvag or ":" in sokvag or "\x00" in sokvag or "~" in sokvag:
        raise Sparrfel(f"Otillåtna tecken i sökvägen: {sokvag}")
    delar = sokvag.split("/")
    for del_ in delar:
        if del_ in ("", ".", ".."):
            raise Sparrfel(f"Ogiltig sökväg: {sokvag}")
    if delar[0] not in TILLATNA_TOPPNIVAER:
        raise Sparrfel(
            f"{delar[0]} är ingen mapp i Livv Marketing Ops. Läs rotmappen och gissa aldrig."
        )
    return "/".join(delar)


def varumarkesmapp(varumarke: str) -> str:
    if varumarke not in VARUMARKESMAPPAR:
        raise Sparrfel(f"Okänt varumärke: {varumarke}. Tillåtna: {', '.join(VARUMARKESMAPPAR)}.")
    return VARUMARKESMAPPAR[varumarke]


def mapp_for_status(status: str, varumarke: str, nu: datetime | None = None) -> str:
    if status not in STATUSMAPPAR:
        raise Sparrfel(f"Okänd status: {status}. Tillåtna: {', '.join(STATUSMAPPAR)}.")
    mapp = f"{STATUSMAPPAR[status]}/{varumarkesmapp(varumarke)}"
    if status == "Arkiverad":
        mapp += "/" + (nu or datetime.now(TIDSZON)).strftime("%Y-%m")
    return mapp


def kontrollera_flytt(fran_status: str, till_status: str) -> None:
    if fran_status == "Arkiverad":
        raise Sparrfel("Ingenting flyttas ut ur 06_Arkiv utan Mattias godkännande. Stoppat.")
    if (fran_status, till_status) not in TILLATNA_FLYTTAR:
        raise Sparrfel(f"Flytten {fran_status} till {till_status} finns inte i statusflödet.")


def kontrollera_filnamn(filnamn: str, varumarke: str, ska_vara_brief: bool) -> re.Match:
    m = FILNAMN_RE.match(filnamn or "")
    if not m:
        raise Sparrfel(
            "Filnamnet följer inte regeln YYYYMMDD_varumarke_kanal_kampanj_format_vNN.md eller .docx: "
            f"{filnamn}"
        )
    if m["varumarke"] != varumarkesmapp(varumarke).lower():
        raise Sparrfel(f"Varumärket i filnamnet stämmer inte med {varumarke}.")
    if ska_vara_brief and m["format"] != "brief":
        raise Sparrfel("En brief ska ha formatet brief i filnamnet.")
    if not ska_vara_brief and m["format"] == "brief":
        raise Sparrfel("Ett utkast får inte ha formatet brief i filnamnet.")
    return m


def text_till_docx(innehall: str) -> bytes:
    from docx import Document

    dok = Document()
    for rad in innehall.splitlines():
        rubrik = re.match(r"^(#{1,3})\s+(.*)$", rad)
        if rubrik:
            dok.add_heading(rubrik[2], level=len(rubrik[1]))
        else:
            dok.add_paragraph(rad)
    buf = io.BytesIO()
    dok.save(buf)
    return buf.getvalue()


def fil_till_text(namn: str, data: bytes) -> str:
    namn_lagt = namn.lower()
    if namn_lagt.endswith((".md", ".txt", ".csv", ".json")):
        return data.decode("utf-8", errors="replace")
    if namn_lagt.endswith(".docx"):
        from docx import Document

        dok = Document(io.BytesIO(data))
        return "\n".join(p.text for p in dok.paragraphs)
    if namn_lagt.endswith(".xlsx"):
        from openpyxl import load_workbook

        bok = load_workbook(io.BytesIO(data), data_only=True)
        delar = []
        for blad in bok.worksheets:
            delar.append(f"## Blad: {blad.title}")
            for rad in blad.iter_rows(values_only=True):
                if any(c is not None for c in rad):
                    delar.append("\t".join("" if c is None else str(c) for c in rad))
        return "\n".join(delar)
    raise Sparrfel(f"Filtypen kan inte läsas som text: {namn}")


# ---------------------------------------------------------------------------
# Excel: register och logg. Logiken följer livv-grund, avsnittet om Excel.
# ---------------------------------------------------------------------------

def _rubriker(blad) -> list[str]:
    return [c.value for c in blad[1] if c.value is not None]


def register_rader(data: bytes, objekt_id: str | None = None) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    blad = load_workbook(io.BytesIO(data))[REGISTER_BLAD]
    rubriker = _rubriker(blad)
    rader = []
    for rad in blad.iter_rows(min_row=2, values_only=True):
        if not any(c is not None for c in rad):
            continue
        post = {k: ("" if v is None else v) for k, v in zip(rubriker, rad)}
        if objekt_id is None or post.get("objekt_id") == objekt_id:
            rader.append(post)
    return rader


def register_andra(data: bytes, objekt_id: str, falt: dict[str, Any], ny: bool) -> bytes:
    """Ändrar bara de berörda cellerna och behåller allt annat i arbetsboken."""
    from openpyxl import load_workbook

    if not OBJEKT_ID_RE.match(objekt_id or ""):
        raise Sparrfel(f"Ogiltigt objekt-ID: {objekt_id}. Format LIVV-2026-0001 eller UNIQ-2026-0001.")
    bok = load_workbook(io.BytesIO(data))
    blad = bok[REGISTER_BLAD]
    rubriker = _rubriker(blad)
    okanda = [k for k in falt if k not in rubriker]
    if okanda:
        raise Sparrfel(f"Okända kolumner: {', '.join(okanda)}. Kolumnnamnen ändras aldrig.")
    if not ny and "objekt_id" in falt and falt["objekt_id"] != objekt_id:
        raise Sparrfel("objekt_id får inte ändras.")

    kol = {namn: i + 1 for i, namn in enumerate(rubriker)}
    radnr = None
    sista = 1
    for r in range(2, blad.max_row + 1):
        if any(blad.cell(r, c).value is not None for c in range(1, len(rubriker) + 1)):
            sista = r
        if blad.cell(r, kol["objekt_id"]).value == objekt_id:
            radnr = r

    if ny:
        if radnr is not None:
            raise Sparrfel(f"{objekt_id} finns redan i registret.")
        radnr = sista + 1
        falt = {**falt, "objekt_id": objekt_id}
    elif radnr is None:
        raise Sparrfel(f"{objekt_id} finns inte i registret.")

    falt = {**falt}
    falt.setdefault("senast_andrad", datetime.now(TIDSZON).strftime("%Y-%m-%d %H:%M"))
    for namn, varde in falt.items():
        blad.cell(radnr, kol[namn]).value = varde

    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


def logg_ny_bok() -> bytes:
    from openpyxl import Workbook

    bok = Workbook()
    bok.active.title = "Logg"
    bok.active.append(LOGG_KOLUMNER)
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


def logg_lagg_till(data: bytes, rad: list[str]) -> bytes:
    from openpyxl import load_workbook

    bok = load_workbook(io.BytesIO(data))
    blad = bok.worksheets[0]
    if _rubriker(blad)[: len(LOGG_KOLUMNER)] != LOGG_KOLUMNER:
        raise Sparrfel("Loggfilens kolumner stämmer inte med livv-grund. Stoppat.")
    blad.append(rad)
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Microsoft Graph
# ---------------------------------------------------------------------------

class Graph:
    """Tunn klient mot Graph. Alla adresser byggs relativt rotmappen."""

    def __init__(self) -> None:
        import httpx
        import msal

        saknas = [n for n in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET") if not os.environ.get(n)]
        if saknas:
            raise Sparrfel(f"Saknar miljövariabler: {', '.join(saknas)}. Se .env.example.")
        self._app = msal.ConfidentialClientApplication(
            os.environ["AZURE_CLIENT_ID"],
            authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
            client_credential=os.environ["AZURE_CLIENT_SECRET"],
        )
        self._http = httpx.Client(timeout=60, follow_redirects=True)

    def _token(self) -> str:
        svar = self._app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in svar:
            raise Sparrfel(f"Inloggning mot Graph misslyckades: {svar.get('error_description', svar)}")
        return svar["access_token"]

    def _anrop(self, metod: str, url: str, **kw):
        kw.setdefault("headers", {})["Authorization"] = f"Bearer {self._token()}"
        svar = self._http.request(metod, url, **kw)
        return svar

    @staticmethod
    def _adress(sokvag: str) -> str:
        bas = f"{GRAPH}/drives/{DRIVE_ID}/items/{ROT_ID}"
        return bas if sokvag == "" else f"{bas}:/{quote(sokvag)}:"

    def finns(self, sokvag: str) -> bool:
        return self._anrop("GET", self._adress(sokvag)).status_code == 200

    def objekt(self, sokvag: str) -> dict:
        svar = self._anrop("GET", self._adress(sokvag))
        if svar.status_code == 404:
            raise Sparrfel(f"Hittar inte {sokvag} i Livv Marketing Ops.")
        svar.raise_for_status()
        return svar.json()

    def lista(self, sokvag: str) -> list[dict]:
        url = self._adress(sokvag) + "/children"
        poster: list[dict] = []
        while url:
            svar = self._anrop("GET", url)
            svar.raise_for_status()
            data = svar.json()
            poster += data.get("value", [])
            url = data.get("@odata.nextLink")
        return poster

    def las(self, sokvag: str) -> bytes:
        svar = self._anrop("GET", self._adress(sokvag) + "/content")
        if svar.status_code == 404:
            raise Sparrfel(f"Hittar inte {sokvag} i Livv Marketing Ops.")
        svar.raise_for_status()
        return svar.content

    def skriv(self, sokvag: str, data: bytes, ersatt: bool) -> dict:
        if len(data) > MAX_FILSTORLEK:
            raise Sparrfel("Filen är större än 4 MB. Stoppat.")
        beteende = "replace" if ersatt else "fail"
        svar = self._anrop(
            "PUT",
            self._adress(sokvag) + f"/content?@microsoft.graph.conflictBehavior={beteende}",
            content=data,
        )
        if svar.status_code == 409:
            raise Sparrfel(f"{sokvag} finns redan. Skriv aldrig över: höj vNN.")
        svar.raise_for_status()
        return svar.json()

    def skapa_mapp_om_saknas(self, sokvag: str) -> None:
        if self.finns(sokvag):
            return
        foralder, _, namn = sokvag.rpartition("/")
        if not foralder:
            raise Sparrfel(f"Huvudmappen {sokvag} saknas. Den skapas aldrig av teamet. Stoppat.")
        self.skapa_mapp_om_saknas(foralder)
        url = self._adress(foralder) + "/children"
        svar = self._anrop(
            "POST", url, json={"name": namn, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
        )
        if svar.status_code not in (200, 201, 409):
            svar.raise_for_status()

    def flytta(self, fran: str, till_mapp: str) -> dict:
        mapp = self.objekt(till_mapp)
        fil = self.objekt(fran)
        svar = self._anrop(
            "PATCH",
            f"{GRAPH}/drives/{DRIVE_ID}/items/{fil['id']}?@microsoft.graph.conflictBehavior=fail",
            json={"parentReference": {"id": mapp["id"]}},
        )
        if svar.status_code == 409:
            raise Sparrfel(f"Det finns redan en fil med samma namn i {till_mapp}. Stoppat.")
        svar.raise_for_status()
        return svar.json()


# ---------------------------------------------------------------------------
# Verktygen. Själva logiken ligger i Livv, så att den kan testas med en låtsas-Graph.
# ---------------------------------------------------------------------------

class Livv:
    def __init__(self, graph) -> None:
        self.g = graph

    def lista_mapp(self, sokvag: str = "") -> list[dict]:
        sokvag = kontrollera_sokvag(sokvag)
        return [
            {
                "namn": p["name"],
                "typ": "mapp" if "folder" in p else "fil",
                "storlek": p.get("size"),
                "andrad": p.get("lastModifiedDateTime"),
                "sokvag": f"{sokvag}/{p['name']}" if sokvag else p["name"],
            }
            for p in self.g.lista(sokvag)
        ]

    def las_fil(self, sokvag: str) -> str:
        sokvag = kontrollera_sokvag(sokvag)
        if not sokvag:
            raise Sparrfel("Ange en fil.")
        return fil_till_text(sokvag, self.g.las(sokvag))

    def _spara_dokument(self, mapp: str, filnamn: str, innehall: str) -> str:
        data = text_till_docx(innehall) if filnamn.endswith(".docx") else innehall.encode("utf-8")
        self.g.skapa_mapp_om_saknas(mapp)
        sokvag = f"{mapp}/{filnamn}"
        self.g.skriv(sokvag, data, ersatt=False)
        return sokvag

    def skapa_brief(self, varumarke: str, filnamn: str, innehall: str) -> str:
        kontrollera_filnamn(filnamn, varumarke, ska_vara_brief=True)
        return self._spara_dokument(mapp_for_status("Brief", varumarke), filnamn, innehall)

    def spara_utkast(self, varumarke: str, filnamn: str, innehall: str) -> str:
        kontrollera_filnamn(filnamn, varumarke, ska_vara_brief=False)
        return self._spara_dokument(mapp_for_status("Utkast", varumarke), filnamn, innehall)

    def spara_rapport(self, filnamn: str, innehall: str) -> str:
        if not RAPPORTNAMN_RE.match(filnamn or ""):
            raise Sparrfel("Rapportnamnet får bara innehålla bokstäver a till z, siffror, _ och - och sluta på .md eller .docx.")
        return self._spara_dokument("08_Rapporter", filnamn, innehall)

    def flytta_objekt(self, filnamn: str, varumarke: str, fran_status: str, till_status: str) -> str:
        kontrollera_flytt(fran_status, till_status)
        if "/" in filnamn or not FILNAMN_RE.match(filnamn):
            raise Sparrfel(f"Ogiltigt filnamn: {filnamn}")
        fran_mapp = mapp_for_status(fran_status, varumarke)
        till_mapp = mapp_for_status(till_status, varumarke)
        if fran_mapp == till_mapp:
            return f"Ingen flytt behövs: filen ligger redan i {till_mapp}."
        self.g.skapa_mapp_om_saknas(till_mapp)
        self.g.flytta(f"{fran_mapp}/{filnamn}", till_mapp)
        return f"Flyttad: {fran_mapp}/{filnamn} till {till_mapp}/{filnamn}"

    def register_las(self, objekt_id: str | None = None) -> list[dict]:
        return register_rader(self.g.las(REGISTER_FIL), objekt_id)

    def _register_skriv(self, objekt_id: str, falt: dict, ny: bool) -> dict:
        data = self.g.las(REGISTER_FIL)  # läs direkt före ändringen, aldrig från en tidigare läsning
        nytt = register_andra(data, objekt_id, falt, ny)
        self.g.skriv(REGISTER_FIL, nytt, ersatt=True)
        kontroll = register_rader(self.g.las(REGISTER_FIL), objekt_id)  # läs tillbaka
        if len(kontroll) != 1 or any(str(kontroll[0].get(k, "")) != str(v) for k, v in falt.items()):
            raise Sparrfel(f"Ändringen av {objekt_id} syns inte när registret läses tillbaka. Stoppa och rapportera.")
        return kontroll[0]

    def register_ny_rad(self, objekt_id: str, falt: dict) -> dict:
        return self._register_skriv(objekt_id, {**falt, "status": falt.get("status", "Brief")}, ny=True)

    def register_uppdatera(self, objekt_id: str, falt: dict) -> dict:
        return self._register_skriv(objekt_id, falt, ny=False)

    def logga(self, agent: str, objekt_id: str, atgard: str, fil_eller_mapp: str, kommentar: str = "") -> str:
        if not re.match(r"^A[0-8]$|^Mattias$", agent or ""):
            raise Sparrfel("Agent ska vara A0 till A8 eller Mattias.")
        nu = datetime.now(TIDSZON)
        sokvag = f"09_Loggar/Logg_{nu:%Y-%m}.xlsx"
        rader = []
        if self.g.finns(sokvag):
            data = self.g.las(sokvag)
        else:
            data = logg_ny_bok()
            rader.append([nu.strftime("%Y-%m-%d"), nu.strftime("%H:%M"), agent, "", "Skapade loggfil", sokvag, "Ny månad"])
        rader.append([nu.strftime("%Y-%m-%d"), nu.strftime("%H:%M"), agent, objekt_id, atgard, fil_eller_mapp, kommentar])
        for rad in rader:
            data = logg_lagg_till(data, rad)
        self.g.skriv(sokvag, data, ersatt=True)
        return f"Loggat i {sokvag}"


def bygg_server(livv_fabrik=None):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        "sharepoint",
        instructions=(
            "Läs och skriv i Livv Marketing Ops enligt livv-grund. "
            "Sökvägar anges relativt rotmappen, till exempel 01_Briefer/Livv."
        ),
    )
    _livv: dict[str, Livv] = {}

    def livv() -> Livv:
        if "x" not in _livv:
            _livv["x"] = (livv_fabrik or (lambda: Livv(Graph())))()
        return _livv["x"]

    @server.tool(description="Lista innehållet i en mapp i Livv Marketing Ops. Tom sökväg ger rotmappen.")
    def lista_mapp(sokvag: str = "") -> list[dict]:
        return livv().lista_mapp(sokvag)

    @server.tool(description="Läs en fil i Livv Marketing Ops som text (md, txt, csv, docx, xlsx).")
    def las_fil(sokvag: str) -> str:
        return livv().las_fil(sokvag)

    @server.tool(description="Skapa en ny brief i 01_Briefer/<varumärke>. Skriver aldrig över. Bara A0.")
    def skapa_brief(varumarke: str, filnamn: str, innehall: str) -> str:
        return livv().skapa_brief(varumarke, filnamn, innehall)

    @server.tool(description="Spara ett nytt utkast i 02_Utkast/<varumärke>. Skriver aldrig över: ny version får nytt vNN.")
    def spara_utkast(varumarke: str, filnamn: str, innehall: str) -> str:
        return livv().spara_utkast(varumarke, filnamn, innehall)

    @server.tool(description="Spara en rapport i 08_Rapporter. Skriver aldrig över.")
    def spara_rapport(filnamn: str, innehall: str) -> str:
        return livv().spara_rapport(filnamn, innehall)

    @server.tool(description="Flytta ett objekts fil vid statusbyte. Servern väljer mapp efter status och varumärke.")
    def flytta_objekt(filnamn: str, varumarke: str, fran_status: str, till_status: str) -> str:
        return livv().flytta_objekt(filnamn, varumarke, fran_status, till_status)

    @server.tool(description="Läs Innehallsregister, hela eller en rad.")
    def register_las(objekt_id: str | None = None) -> list[dict]:
        return livv().register_las(objekt_id)

    @server.tool(description="Lägg till en ny rad i Innehallsregister. Bara A0.")
    def register_ny_rad(objekt_id: str, falt: dict) -> dict:
        return livv().register_ny_rad(objekt_id, falt)

    @server.tool(description="Uppdatera fält på en befintlig rad i Innehallsregister.")
    def register_uppdatera(objekt_id: str, falt: dict) -> dict:
        return livv().register_uppdatera(objekt_id, falt)

    @server.tool(description="Logga en åtgärd i 09_Loggar/Logg_YYYY-MM.xlsx.")
    def logga(agent: str, objekt_id: str, atgard: str, fil_eller_mapp: str, kommentar: str = "") -> str:
        return livv().logga(agent, objekt_id, atgard, fil_eller_mapp, kommentar)

    return server


if __name__ == "__main__":
    bygg_server().run("stdio")
