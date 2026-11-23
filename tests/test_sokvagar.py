"""Tester för MCP-servern utan nätverk.

Kör: python3 -m unittest discover -s tests
En låtsas-Graph håller filerna i minnet, så inget anrop når SharePoint.
"""

import io
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp"))

import sharepoint_server as s  # noqa: E402

KOLUMNER = (
    "objekt_id varumarke kanal kampanj malgrupp syfte sprak format titel status prioritet "
    "ansvarig_agent filnamn mapp version briefdatum kallor granskad_a3_datum a3_utfall "
    "revideringsvarv eskalera eskalera_skal sakerhet godkand_av godkand_datum "
    "planerad_publicering publicerad_datum plattforms_id url resultat_30d "
    "avvisningsmotivering senast_andrad"
).split()


def testregister() -> bytes:
    from openpyxl import Workbook

    bok = Workbook()
    blad = bok.active
    blad.title = "Register"
    blad.append(KOLUMNER)
    blad.append(["LIVV-2026-0001", "Livv"] + [None] * (len(KOLUMNER) - 2))
    bok.create_sheet("Statusflode").append(["Status", "Mapp"])
    bok.create_sheet("Kolumner").append(["Kolumn"])
    dold = bok.create_sheet("Listor")
    dold.sheet_state = "hidden"
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


class LatsasGraph:
    def __init__(self):
        self.filer = {"Innehallsregister.xlsx": testregister()}
        self.mappar = {"01_Briefer", "02_Utkast", "03_Granskning", "04_Godkant", "06_Arkiv", "09_Loggar"}
        self.flyttar = []

    def finns(self, sokvag):
        return sokvag in self.filer or sokvag in self.mappar

    def las(self, sokvag):
        if sokvag not in self.filer:
            raise s.Sparrfel(f"Hittar inte {sokvag}")
        return self.filer[sokvag]

    def skriv(self, sokvag, data, ersatt):
        if sokvag in self.filer and not ersatt:
            raise s.Sparrfel("finns redan")
        self.filer[sokvag] = data

    def skapa_mapp_om_saknas(self, sokvag):
        self.mappar.add(sokvag)

    def flytta(self, fran, till_mapp):
        namn = fran.rsplit("/", 1)[1]
        self.filer[f"{till_mapp}/{namn}"] = self.filer.pop(fran)
        self.flyttar.append((fran, till_mapp))

    def lista(self, sokvag):
        return []


class TestSokvagar(unittest.TestCase):
    def test_tillatna(self):
        self.assertEqual(s.kontrollera_sokvag("01_Briefer/Livv/"), "01_Briefer/Livv")
        self.assertEqual(s.kontrollera_sokvag(""), "")

    def test_otillatna(self):
        for dalig in ["../annat", "01_Briefer/../../x", "/etc/passwd", "Annan mapp/fil",
                      "01_Briefer\\x", "01_Briefer:/x", "01_Briefer//x", "~/x"]:
            with self.subTest(dalig=dalig):
                with self.assertRaises(s.Sparrfel):
                    s.kontrollera_sokvag(dalig)

    def test_statusmappar(self):
        nu = datetime(2026, 11, 15)
        self.assertEqual(s.mapp_for_status("Granskning", "Livv Group"), "03_Granskning/LivvGroup")
        self.assertEqual(s.mapp_for_status("Arkiverad", "Unique", nu), "06_Arkiv/Unique/2026-11")
        with self.assertRaises(s.Sparrfel):
            s.mapp_for_status("Raderad", "Livv")
        with self.assertRaises(s.Sparrfel):
            s.mapp_for_status("Brief", "Okänt")

    def test_flyttar(self):
        s.kontrollera_flytt("Utkast", "Granskning")
        for fran, till in [("Arkiverad", "Publicerad"), ("Brief", "Godkänd"), ("Utkast", "Godkänd")]:
            with self.subTest(fran=fran, till=till):
                with self.assertRaises(s.Sparrfel):
                    s.kontrollera_flytt(fran, till)

    def test_filnamn(self):
        s.kontrollera_filnamn("20261116_livv_linkedin_vinter_brief_v01.md", "Livv", True)
        s.kontrollera_filnamn("20261116_unique_meta_vinter_karusell_v02.docx", "Unique", False)
        for namn, varumarke, brief in [
            ("20261116_livv_linkedin_vinter_brief_v01.md", "Livv", False),
            ("20261116_livv_linkedin_vinter_inlagg_v01.md", "Livv", True),
            ("20261116_livv_linkedin_vinter_inlagg_v01.md", "Unique", False),
            ("utkast.md", "Livv", False),
            ("20261116_livv_linkedin_vinter_inlagg_v1.md", "Livv", False),
        ]:
            with self.subTest(namn=namn):
                with self.assertRaises(s.Sparrfel):
                    s.kontrollera_filnamn(namn, varumarke, brief)


class TestLoopen(unittest.TestCase):
    def setUp(self):
        self.g = LatsasGraph()
        self.livv = s.Livv(self.g)

    def test_utkast_skrivs_aldrig_over(self):
        namn = "20261116_livv_linkedin_vinter_inlagg_v01.md"
        self.livv.spara_utkast("Livv", namn, "Text")
        with self.assertRaises(s.Sparrfel):
            self.livv.spara_utkast("Livv", namn, "Ny text")

    def test_docx_skapas(self):
        sokvag = self.livv.skapa_brief("Livv", "20261116_livv_linkedin_vinter_brief_v01.docx", "# Brief\nSyfte")
        self.assertIn("Syfte", s.fil_till_text(sokvag, self.g.filer[sokvag]))

    def test_flytt_och_arkiv(self):
        namn = "20261116_livv_linkedin_vinter_inlagg_v01.md"
        self.livv.spara_utkast("Livv", namn, "Text")
        self.livv.flytta_objekt(namn, "Livv", "Utkast", "Granskning")
        self.assertIn(f"03_Granskning/Livv/{namn}", self.g.filer)
        with self.assertRaises(s.Sparrfel):
            self.livv.flytta_objekt(namn, "Livv", "Arkiverad", "Utkast")

    def test_register_behaller_blad_och_andrar_bara_falt(self):
        self.livv.register_ny_rad("LIVV-2026-0002", {"varumarke": "Livv", "kanal": "LinkedIn"})
        rad = self.livv.register_uppdatera("LIVV-2026-0002", {"a3_utfall": "Godkänd"})
        self.assertEqual(rad["kanal"], "LinkedIn")
        self.assertEqual(rad["status"], "Brief")
        from openpyxl import load_workbook

        bok = load_workbook(io.BytesIO(self.g.filer["Innehallsregister.xlsx"]))
        self.assertEqual(bok.sheetnames, ["Register", "Statusflode", "Kolumner", "Listor"])
        self.assertEqual(bok["Listor"].sheet_state, "hidden")
        self.assertEqual(len(s.register_rader(self.g.filer["Innehallsregister.xlsx"])), 2)

    def test_register_stoppar(self):
        with self.assertRaises(s.Sparrfel):
            self.livv.register_ny_rad("LIVV-2026-0001", {})  # finns redan
        with self.assertRaises(s.Sparrfel):
            self.livv.register_uppdatera("LIVV-2026-0001", {"ny_kolumn": "x"})
        with self.assertRaises(s.Sparrfel):
            self.livv.register_uppdatera("LIVV-2026-0099", {"status": "Utkast"})
        with self.assertRaises(s.Sparrfel):
            self.livv.register_ny_rad("livv-1", {})

    def test_logg_skapar_manadsfil(self):
        self.livv.logga("A3", "LIVV-2026-0001", "Granskad", "02_Utkast/Livv")
        sokvag = next(k for k in self.g.filer if k.startswith("09_Loggar/"))
        text = s.fil_till_text(sokvag, self.g.filer[sokvag])
        self.assertIn("Skapade loggfil", text)
        self.assertIn("Granskad", text)
        with self.assertRaises(s.Sparrfel):
            self.livv.logga("A9", "LIVV-2026-0001", "x", "y")


class TestIngenBildtext(unittest.TestCase):
    """A4 skriver aldrig text till bilden. Servern stoppar utkast som gör det."""

    UTKAST = "## Inläggstext\nGästen sover bättre.\n\n## Anteckningar\n{rad}\n"

    def test_stoppas(self):
        for rad in ["Text på bilden: Sov gott", "**Förslag på text i bilden:** Sov gott", "- Bildtext: Sov gott",
                    "### Rubrik på bilden", "Image text: Sleep well", "Text overlay: Sleep well",
                    "1. Headline on the image: Sleep well", "Overlay: Sleep well", "Suggested copy for the visual: x"]:
            with self.subTest(rad=rad):
                with self.assertRaises(s.Sparrfel) as fel:
                    s.Livv(LatsasGraph()).spara_utkast("Livv", "20261116_livv_linkedin_vinter_inlagg_v01.md",
                                                       self.UTKAST.format(rad=rad))
                self.assertIn("text till bilden", str(fel.exception))

    def test_vanlig_text_slapps_igenom(self):
        for rad in ["Källa: 00_Underlag/Produktblad.pdf", "Texten bygger på lärdomen om CTA.",
                    "Bilden tas fram av Brand Studio.", "Vi valde en fråga i slutet."]:
            with self.subTest(rad=rad):
                s.Livv(LatsasGraph()).spara_utkast("Livv", "20261116_livv_linkedin_vinter_inlagg_v01.md",
                                                   self.UTKAST.format(rad=rad))


if __name__ == "__main__":
    unittest.main()
