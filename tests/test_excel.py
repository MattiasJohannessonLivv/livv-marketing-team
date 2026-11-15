"""Tester för att Excel-filerna överlever en skrivning via MCP-servern.

Kör: python3 -m unittest discover -s tests

Testfilerna byggs så som Excel sparar dem: rullistor både i klassisk form och som
x14-tillägg (listor som pekar på det dolda bladet Listor), cellformat, delade
strängar och en tabell. Verktygen anropas genom MCP-servern med en låtsas-Graph,
så inget anrop når SharePoint.

Riktiga kopior: lägg Innehallsregister.xlsx och en Logg_YYYY-MM.xlsx i en mapp och kör
    LIVV_KOPIOR=/sökväg/till/mappen python3 -m unittest discover -s tests
Kopiorna läses bara. Inget skrivs tillbaka till mappen.
"""

import asyncio
import io
import json
import os
import re
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sharepoint_server as s  # noqa: E402
from test_sokvagar import KOLUMNER, LatsasGraph  # noqa: E402

X14 = (
    '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}" '
    'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
    '<x14:dataValidations count="1" xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main">'
    '<x14:dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1">'
    "<x14:formula1><xm:f>Listor!$B$1:$B$9</xm:f></x14:formula1><xm:sqref>{sqref}</xm:sqref>"
    "</x14:dataValidation></x14:dataValidations></ext></extLst>"
)


def _med_x14(data: bytes, bladdel: str, sqref: str) -> bytes:
    """Lägger in en x14-rullista som Excel gör. openpyxl kan inte skriva den själv."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    ut = io.BytesIO()
    with zipfile.ZipFile(ut, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            innehall = zin.read(info.filename)
            if info.filename == bladdel:
                innehall = innehall.replace(b"</worksheet>", X14.replace("{sqref}", sqref).encode() + b"</worksheet>")
            zout.writestr(info, innehall)
    return ut.getvalue()


def excel_register(med_tabell: bool = False) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.worksheet.table import Table

    bok = Workbook()
    blad = bok.active
    blad.title = "Register"
    blad.append(KOLUMNER)
    for c in blad[1]:
        c.font = Font(bold=True)
    blad.append(["LIVV-2026-0001", "Livv", "LinkedIn", "vinter"] + [None] * 5 + ["Brief"] + [None] * (len(KOLUMNER) - 10))
    for c in blad[2]:
        c.fill = PatternFill("solid", fgColor="FFF2CC")
    bok.create_sheet("Statusflode").append(["Status", "Mapp"])
    bok.create_sheet("Kolumner").append(["Kolumn"])
    listor = bok.create_sheet("Listor")
    listor.sheet_state = "hidden"
    for i, (status, kanal) in enumerate(zip(
        ["Brief", "Utkast", "Granskning", "Godkänd", "Schemalagd", "Publicerad", "Arkiverad", "Avvisad", ""],
        ["LinkedIn", "Meta", "Google", "X", "Webb", "Nyhetsbrev", "", "", ""],
    ), 1):
        listor.cell(i, 1).value = status or None
        listor.cell(i, 2).value = kanal or None

    status = get_column_letter(KOLUMNER.index("status") + 1)
    dv = DataValidation(type="list", formula1="=Listor!$A$1:$A$8", allow_blank=True)
    dv.add(f"{status}2:{status}1000")
    blad.add_data_validation(dv)
    if med_tabell:
        sista = get_column_letter(len(KOLUMNER))
        blad.add_table(Table(displayName="Register", ref=f"A1:{sista}2"))

    buf = io.BytesIO()
    bok.save(buf)
    kanal = get_column_letter(KOLUMNER.index("kanal") + 1)
    return _med_x14(buf.getvalue(), "xl/worksheets/sheet1.xml", f"{kanal}2:{kanal}1000")


def excel_logg() -> bytes:
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    bok = Workbook()
    blad = bok.active
    blad.title = "Logg"
    blad.append(s.LOGG_KOLUMNER)
    blad.append(["2026-11-01", "08:00", "A0", "", "Skapade loggfil", "09_Loggar/Logg_2026-11.xlsx", "Ny månad"])
    agenter = bok.create_sheet("Listor")
    agenter.sheet_state = "hidden"
    for i, a in enumerate([f"A{n}" for n in range(9)] + ["Mattias"], 1):
        agenter.cell(i, 1).value = a
    dv = DataValidation(type="list", formula1="=Listor!$A$1:$A$10")
    dv.add("C2:C5000")
    blad.add_data_validation(dv)
    buf = io.BytesIO()
    bok.save(buf)
    return _med_x14(buf.getvalue(), "xl/worksheets/sheet1.xml", "C2:C5000")


# ---------------------------------------------------------------------------
# Jämförelse före och efter
# ---------------------------------------------------------------------------

def _delar(data: bytes) -> dict[str, bytes]:
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: z.read(n) for n in z.namelist()}


def _bladdel(data: bytes, bladnamn: str) -> str:
    return s._bladets_delar(_delar(data), bladnamn)


def rullistor(data: bytes) -> dict[str, list[str]]:
    """Alla rullistor per blad, klassiska och x14, som text."""
    delar = _delar(data)
    from openpyxl import load_workbook

    namn = load_workbook(io.BytesIO(data), read_only=True).sheetnames
    ut = {}
    for blad in namn:
        xml = delar[s._bladets_delar(delar, blad)].decode("utf-8")
        ut[blad] = re.findall(r"<dataValidations\b.*?</dataValidations>", xml, re.S) + re.findall(
            r"<x14:dataValidations\b.*?</x14:dataValidations>", xml, re.S)
    return ut


def blad_och_synlighet(data: bytes) -> list[tuple[str, str]]:
    from openpyxl import load_workbook

    with __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        bok = load_workbook(io.BytesIO(data))
    return [(b.title, b.sheet_state) for b in bok.worksheets]


def anropa(server, verktyg: str, argument: dict):
    svar = asyncio.run(server.call_tool(verktyg, argument))
    text = svar.content[0].text
    try:
        return json.loads(text)
    except ValueError:
        return text


class ExcelFall:
    """Gemensamma kontroller. Körs mot testfilerna och mot riktiga kopior om de finns."""

    register: bytes
    logg: bytes | None = None

    def setUp(self):
        self.g = LatsasGraph()
        self.g.filer["Innehallsregister.xlsx"] = self.register
        self.server = s.bygg_server(lambda: s.Livv(self.g))
        self.fore = self.register

    def _nasta_id(self) -> str:
        rader = s.register_rader(self.fore)
        hogsta = max([int(r["objekt_id"][-4:]) for r in rader if str(r.get("objekt_id", "")).startswith("LIVV-2026-")] or [0])
        return f"LIVV-2026-{hogsta + 1:04d}"

    def test_register_ny_rad_och_uppdatering_behaller_allt(self):
        objekt_id = self._nasta_id()
        anropa(self.server, "register_ny_rad", {"objekt_id": objekt_id, "falt": {"varumarke": "Livv", "kanal": "LinkedIn"}})
        rad = anropa(self.server, "register_uppdatera", {"objekt_id": objekt_id, "falt": {"status": "Utkast", "revideringsvarv": 1}})
        self.assertEqual(rad["kanal"], "LinkedIn")
        self.assertEqual(rad["status"], "Utkast")
        efter = self.g.filer["Innehallsregister.xlsx"]

        self.assertEqual(rullistor(self.fore), rullistor(efter), "Rullistorna har ändrats")
        self.assertEqual(blad_och_synlighet(self.fore), blad_och_synlighet(efter))
        andrade = {n for n, d in _delar(efter).items() if _delar(self.fore).get(n) != d}
        tillatna = {_bladdel(self.fore, "Register")} | {n for n in andrade if n.startswith("xl/tables/")}
        self.assertLessEqual(andrade, tillatna, f"Andra delar än registerbladet ändrades: {andrade - tillatna}")
        self.assertEqual(set(_delar(efter)), set(_delar(self.fore)), "Delar har tillkommit eller försvunnit")

        rader_fore = s.register_rader(self.fore)
        rader_efter = s.register_rader(efter)
        self.assertEqual(rader_efter[: len(rader_fore)], rader_fore, "Befintliga rader har ändrats")
        self.assertEqual(len(rader_efter), len(rader_fore) + 1)

    def test_loggens_kolumner_stammer_med_livv_grund(self):
        grund = (Path(__file__).resolve().parent.parent / ".claude/skills/livv-grund/SKILL.md").read_text("utf-8")
        rad = re.search(r"Logg_YYYY-MM\.xlsx: (.*?)\.\n", grund)[1]
        self.assertEqual([k.strip() for k in rad.split(",")], s.LOGG_KOLUMNER)
        if self.logg is None:
            self.skipTest("Ingen loggkopia")
        s.logg_kontrollera_kolumner(self.logg)

    def test_logga_behaller_rullistor(self):
        if self.logg is None:
            self.skipTest("Ingen loggkopia")
        sokvag = f"09_Loggar/Logg_{s.datetime.now(s.TIDSZON):%Y-%m}.xlsx"
        self.g.filer[sokvag] = self.logg
        anropa(self.server, "logga", {"agent": "A0", "objekt_id": "LIVV-2026-0001", "atgard": "Test", "fil_eller_mapp": "01_Briefer/Livv"})
        efter = self.g.filer[sokvag]
        self.assertEqual(rullistor(self.logg), rullistor(efter))
        self.assertEqual(blad_och_synlighet(self.logg), blad_och_synlighet(efter))
        text = s.fil_till_text(sokvag, efter)
        self.assertEqual(text.splitlines()[1].split("\t")[:7], s.LOGG_KOLUMNER)
        self.assertIn("A0\tLIVV-2026-0001\tTest\t01_Briefer/Livv", text)


class TestExcelTestfiler(ExcelFall, unittest.TestCase):
    register = excel_register()
    logg = excel_logg()

    def test_openpyxl_ensam_hade_tappat_x14(self):
        """Visar varför servern inte sparar om arbetsboken med openpyxl."""
        import warnings
        from openpyxl import load_workbook

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bok = load_workbook(io.BytesIO(self.register))
        buf = io.BytesIO()
        bok.save(buf)
        self.assertNotEqual(rullistor(self.register)["Register"], rullistor(buf.getvalue())["Register"])

    def test_ny_rad_far_samma_format_som_raden_ovanfor(self):
        from openpyxl import load_workbook

        anropa(self.server, "register_ny_rad", {"objekt_id": "LIVV-2026-0002", "falt": {"varumarke": "Livv"}})
        blad = load_workbook(io.BytesIO(self.g.filer["Innehallsregister.xlsx"]))["Register"]
        self.assertEqual(blad["B3"].fill.fgColor.rgb, blad["B2"].fill.fgColor.rgb)

    def test_tabell_vaxer_med_ny_rad(self):
        self.g.filer["Innehallsregister.xlsx"] = excel_register(med_tabell=True)
        anropa(self.server, "register_ny_rad", {"objekt_id": "LIVV-2026-0002", "falt": {"varumarke": "Livv"}})
        delar = _delar(self.g.filer["Innehallsregister.xlsx"])
        tabell = next(d for n, d in delar.items() if n.startswith("xl/tables/")).decode()
        self.assertRegex(tabell, r'<table\b[^>]*\sref="A1:[A-Z]+3"')

    def test_fel_loggkolumner_stoppar(self):
        from openpyxl import Workbook

        bok = Workbook()
        bok.active.append(["Datum", "Tid", "Agent", "Objekt", "Åtgärd", "Fil", "Kommentar"])
        buf = io.BytesIO()
        bok.save(buf)
        with self.assertRaises(s.Sparrfel):
            s.logg_lagg_till(buf.getvalue(), ["x"] * 7)

    def test_formelcell_skrivs_inte_over(self):
        from openpyxl import load_workbook

        bok = load_workbook(io.BytesIO(excel_register()))
        bok["Register"]["C2"] = "=Listor!B1"
        buf = io.BytesIO()
        bok.save(buf)
        with self.assertRaises(s.Sparrfel):
            s.register_andra(buf.getvalue(), "LIVV-2026-0001", {"kanal": "Meta"}, ny=False)


KOPIOR = os.environ.get("LIVV_KOPIOR")


@unittest.skipUnless(KOPIOR and (Path(KOPIOR or ".") / "Innehallsregister.xlsx").is_file(),
                     "Sätt LIVV_KOPIOR till en mapp med kopior av Innehallsregister.xlsx och en loggfil")
class TestRiktigaKopior(ExcelFall, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mapp = Path(KOPIOR)
        cls.register = (mapp / "Innehallsregister.xlsx").read_bytes()
        loggar = sorted(mapp.glob("Logg_*.xlsx"))
        cls.logg = loggar[-1].read_bytes() if loggar else None


if __name__ == "__main__":
    unittest.main()
