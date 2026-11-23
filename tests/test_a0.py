"""A0 startas i bakgrunden när Mattias godkänt i tavlan, så att bildbriefen skrivs direkt.

Claude Code ersätts av en attrapp. Inget startas på riktigt.
Kör: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "tavla"))
sys.path.insert(0, str(ROT / "mcp"))

import a0  # noqa: E402
import beslut as b  # noqa: E402
import sharepoint_server as sp  # noqa: E402
from test_beslut import LasVy, grund  # noqa: E402


class Process:
    def __init__(self, klar=False):
        self.klar = klar

    def poll(self):
        return 0 if self.klar else None


class Starta:
    def __init__(self, fel=None):
        self.anrop, self.fel = [], fel

    def __call__(self, argument, **kw):
        if self.fel:
            raise self.fel
        self.anrop.append((argument, kw))
        return Process()


def startare(starta, hitta=lambda namn: "/usr/local/bin/claude", miljo=None):
    return a0.Bildbriefstartare(starta=starta, hitta=hitta, miljo=miljo if miljo is not None else {},
                                loggmapp=Path(tempfile.mkdtemp()))


class TestStartaren(unittest.TestCase):
    def test_startar_a0_i_drift_med_fa_verktyg(self):
        starta = Starta()
        svar = startare(starta, miljo={"LIVV_UTVECKLING": "1", "AZURE_CLIENT_ID": "x"})("LIVV-2026-0003")
        self.assertIn("A0 skriver bildbriefen nu", svar)
        argument, kw = starta.anrop[0]
        self.assertEqual(argument[:2], ["/usr/local/bin/claude", "-p"])
        self.assertIn("LIVV-2026-0003", argument[2])
        self.assertIn("5b", argument[2])
        tillatna = argument[argument.index("--allowedTools") + 1].split(",")
        self.assertEqual(set(tillatna), {"mcp__sharepoint__lista_mapp", "mcp__sharepoint__las_fil",
                                         "mcp__sharepoint__register_las", "mcp__sharepoint__spara_bildbrief",
                                         "mcp__sharepoint__logga"})
        sparrade = argument[argument.index("--disallowedTools") + 1].split(",")
        for verktyg in ("Bash", "Write", "Edit", "mcp__sharepoint__flytta_objekt", "mcp__sharepoint__register_uppdatera"):
            self.assertIn(verktyg, sparrade)
        self.assertEqual(kw["env"]["LIVV_UTVECKLING"], "0", "Körningen ska alltid vara i driftläge")
        self.assertEqual(kw["env"]["AZURE_CLIENT_ID"], "x", "SharePoint-servern behöver tavlans inställningar")
        self.assertEqual(kw["cwd"], str(a0.ROT))

    def test_bara_en_korning_per_objekt(self):
        starta = Starta()
        s = startare(starta)
        s("LIVV-2026-0003")
        self.assertIn("redan", s("LIVV-2026-0003"))
        s("LIVV-2026-0004")
        self.assertEqual(len(starta.anrop), 2)

    def test_utan_claude_eller_vid_fel(self):
        self.assertIn("nästa gång du startar teamet", startare(Starta(), hitta=lambda n: None)("LIVV-2026-0003"))
        self.assertIn("nästa gång du startar teamet", startare(Starta(fel=OSError("nej")))("LIVV-2026-0003"))

    def test_ogiltigt_id(self):
        starta = Starta()
        self.assertIn("ogiltigt", startare(starta)("LIVV-2026-0003; rm -rf /"))
        self.assertEqual(starta.anrop, [])


class TestGodkannStartarA0(unittest.TestCase):
    def test_godkannande_startar_a0(self):
        g = grund()
        startade = []
        beslut = b.Beslut(LasVy(g), g, efter_godkannande=lambda i: startade.append(i) or "A0 skriver bildbriefen nu.")
        svar = beslut.godkann("LIVV-2026-0002")
        self.assertEqual(startade, ["LIVV-2026-0002"])
        self.assertIn("är godkänd", svar)
        self.assertIn("A0 skriver bildbriefen nu.", svar)

    def test_godkannandet_galler_aven_om_a0_inte_startar(self):
        g = grund()

        def trasig(objekt_id):
            raise RuntimeError("x")

        svar = b.Beslut(LasVy(g), g, efter_godkannande=trasig).godkann("LIVV-2026-0002")
        self.assertIn("är godkänd", svar)
        self.assertIn("nästa gång du startar teamet", svar)
        self.assertEqual(sp.register_rader(g.filer[sp.REGISTER_FIL], "LIVV-2026-0002")[0]["status"], "Godkänd")

    def test_inget_startas_nar_godkannandet_stoppas(self):
        g = grund(status="Utkast")
        startade = []
        with self.assertRaises(sp.Sparrfel):
            b.Beslut(LasVy(g), g, efter_godkannande=startade.append).godkann("LIVV-2026-0002")
        self.assertEqual(startade, [])

    def test_servern_startar_a0(self):
        kod = (ROT / "tavla/server.py").read_text(encoding="utf-8")
        self.assertIn("efter_godkannande=Bildbriefstartare()", kod)


if __name__ == "__main__":
    unittest.main()
