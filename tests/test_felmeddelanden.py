"""Verktygen visar alltid den verkliga orsaken när något går fel.

MCP-biblioteket visar bara "Error executing tool <namn>" för fel som inte är ToolError.
Så såg felet i logga ut mot 09_Loggar/Logg_2026-11.xlsx: orsaken syntes aldrig.

Kör: python3 -m unittest discover -s tests
"""

import asyncio
import io
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sharepoint_server as s  # noqa: E402
from test_sokvagar import LatsasGraph  # noqa: E402

BAS = f"{s.GRAPH}/drives/{s.DRIVE_ID}/items/{s.ROT_ID}"


def http_fel(kod: int, url: str, kropp: dict | None = None):
    import httpx

    req = httpx.Request("PUT", url)
    return httpx.HTTPStatusError(str(kod), request=req, response=httpx.Response(kod, request=req, json=kropp))


class LastLogg(LatsasGraph):
    """SharePoint svarar 423 när loggfilen är öppen i Excel. Läsning fungerar ändå."""

    def skriv(self, sokvag, data, ersatt):
        if sokvag.startswith("09_Loggar/"):
            raise http_fel(423, f"{BAS}:/{sokvag}:/content",
                           {"error": {"code": "resourceLocked", "message": "The resource you are attempting to access is locked"}})
        super().skriv(sokvag, data, ersatt)


def loggfil() -> bytes:
    from openpyxl import Workbook

    bok = Workbook()
    bok.active.title = "Logg"
    bok.active.append(s.LOGG_KOLUMNER)
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


def anropa(server, verktyg, argument):
    """Svaret som agenten ser, även när verktyget misslyckas."""
    try:
        svar = asyncio.run(server.call_tool(verktyg, argument))
        return svar.content[0].text
    except Exception as fel:  # samma text som når agenten som is_error
        return str(fel)


class TestVerkligOrsak(unittest.TestCase):
    def server(self, g):
        return s.bygg_server(lambda: s.Livv(g))

    def test_last_loggfil_visar_orsaken(self):
        g = LastLogg()
        g.filer[f"09_Loggar/Logg_{datetime.now(s.TIDSZON):%Y-%m}.xlsx"] = loggfil()
        text = anropa(self.server(g), "logga", {"agent": "A0", "objekt_id": "LIVV-2026-0001",
                                                "atgard": "Test", "fil_eller_mapp": "01_Briefer/Livv"})
        self.assertIn("423", text)
        self.assertIn("Logg_", text)
        self.assertIn("låst", text)
        self.assertIn("resourceLocked", text)
        self.assertNotEqual(text.strip(), "Error executing tool logga")

    def test_sparrfel_visas(self):
        text = anropa(self.server(LatsasGraph()), "logga", {"agent": "A9", "objekt_id": "", "atgard": "x", "fil_eller_mapp": "y"})
        self.assertIn("Agent ska vara A0 till A8 eller Mattias", text)

    def test_fel_kolumner_visas(self):
        from openpyxl import Workbook

        g = LatsasGraph()
        bok = Workbook()
        bok.active.append(["Datum", "Tid", "Agent", "Objekt", "Åtgärd", "Fil", "Kommentar"])
        buf = io.BytesIO()
        bok.save(buf)
        g.filer[f"09_Loggar/Logg_{datetime.now(s.TIDSZON):%Y-%m}.xlsx"] = buf.getvalue()
        text = anropa(self.server(g), "logga", {"agent": "A0", "objekt_id": "", "atgard": "x", "fil_eller_mapp": "y"})
        self.assertIn("Loggfilens kolumner stämmer inte", text)
        self.assertIn("Objekt,", text)

    def test_oväntat_fel_visar_typ_och_text(self):
        class Trasig(LatsasGraph):
            def las(self, sokvag):
                raise ValueError("oväntat innehåll i filen")

        text = anropa(self.server(Trasig()), "register_las", {})
        self.assertIn("ValueError: oväntat innehåll i filen", text)

    def test_alla_verktyg_ger_orsaken(self):
        server = self.server(LatsasGraph())
        verktyg = asyncio.run(server.list_tools())
        self.assertEqual(len(verktyg), 12)
        las = next(v for v in verktyg if v.name == "las_fil")
        self.assertIn("sokvag", las.input_schema["properties"])  # schemat följer med genom omslaget
        self.assertIn("Annan_mapp är ingen mapp", anropa(server, "las_fil", {"sokvag": "Annan_mapp/x.md"}))

    def test_felbeskrivning_utan_graphtext(self):
        fel = http_fel(503, f"{BAS}:/Innehallsregister.xlsx:/content")
        self.assertIn("tillfälligt fel hos Microsoft", s.felbeskrivning(fel))
        self.assertIn("Innehallsregister.xlsx", s.felbeskrivning(fel))

    def test_ogiltiga_xml_tecken_tas_bort(self):
        data = s.logg_lagg_till(loggfil(), ["2026-11-23", "09:00", "A0", "", "x", "y", "rad\x0bbrytning\x00"])
        self.assertIn("radbrytning", s.fil_till_text("Logg.xlsx", data))


if __name__ == "__main__":
    unittest.main()
