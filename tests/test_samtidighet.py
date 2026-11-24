"""Två skrivare samtidigt får aldrig skriva över varandra i registret eller loggen.

Registret och loggen skrivs om som hela filer. Servern skriver bara om filen har
samma version som när den lästes, och gör annars om ändringen på den nya versionen.
Kör: python3 -m unittest discover -s tests
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sharepoint_server as s  # noqa: E402
from test_felmeddelanden import loggfil  # noqa: E402
from test_sokvagar import LatsasGraph  # noqa: E402


class VersionsGraph(LatsasGraph):
    """Som SharePoint: varje fil har en version, och skriv med om_version kräver samma version."""

    def __init__(self):
        super().__init__()
        self.versioner = {}
        self.innan_skrivning = []  # funktioner som körs före nästa skrivning, för att simulera en annan skrivare

    def las_med_version(self, sokvag):
        return self.las(sokvag), str(self.versioner.get(sokvag, 0))

    def skriv(self, sokvag, data, ersatt, om_version=None):
        while self.innan_skrivning:
            self.innan_skrivning.pop(0)()
        if sokvag in self.filer and not ersatt:
            raise s.Skrivkrock("finns redan")
        if om_version is not None and om_version != str(self.versioner.get(sokvag, 0)):
            raise s.Skrivkrock("ändrad")
        self.filer[sokvag] = data
        self.versioner[sokvag] = self.versioner.get(sokvag, 0) + 1


class TestSamtidighet(unittest.TestCase):
    def setUp(self):
        s.Livv.FORSOK = 5
        self.g = VersionsGraph()
        self.livv = s.Livv(self.g)
        self.annan = s.Livv(self.g)

    def test_registret_tappar_ingen_andring(self):
        # En annan agent hinner skriva en ny rad mellan vår läsning och vår skrivning
        self.g.innan_skrivning.append(lambda: self.annan.register_ny_rad("LIVV-2026-0003", {"varumarke": "Livv"}))
        self.livv.register_uppdatera("LIVV-2026-0001", {"kanal": "LinkedIn"})
        rader = {r["objekt_id"]: r for r in s.register_rader(self.g.filer[s.REGISTER_FIL])}
        self.assertIn("LIVV-2026-0003", rader, "Den andra agentens rad försvann")
        self.assertEqual(rader["LIVV-2026-0001"]["kanal"], "LinkedIn", "Vår ändring försvann")

    def test_loggen_tappar_ingen_rad(self):
        sokvag = f"09_Loggar/Logg_{datetime.now(s.TIDSZON):%Y-%m}.xlsx"
        self.g.filer[sokvag] = loggfil()
        self.g.innan_skrivning.append(lambda: self.annan.logga("A3", "LIVV-2026-0001", "Granskade", "x"))
        self.livv.logga("A4", "LIVV-2026-0001", "Sparade utkast", "y")
        text = s.fil_till_text(sokvag, self.g.filer[sokvag])
        self.assertIn("Granskade", text)
        self.assertIn("Sparade utkast", text)

    def test_ny_loggfil_samtidigt(self):
        sokvag = f"09_Loggar/Logg_{datetime.now(s.TIDSZON):%Y-%m}.xlsx"
        self.g.innan_skrivning.append(lambda: self.annan.logga("A3", "", "Först", "x"))
        self.livv.logga("A4", "", "Sedan", "y")
        text = s.fil_till_text(sokvag, self.g.filer[sokvag])
        self.assertIn("Först", text)
        self.assertIn("Sedan", text)
        self.assertEqual(text.count("Skapade loggfil"), 1)

    def test_ger_upp_med_tydligt_besked(self):
        s.Livv.FORSOK = 2
        for _ in range(10):
            self.g.innan_skrivning.append(lambda: self.g.versioner.__setitem__(s.REGISTER_FIL, self.g.versioner.get(s.REGISTER_FIL, 0) + 1))
        orig = self.g.skriv

        def alltid_krock(sokvag, data, ersatt, om_version=None):
            self.g.versioner[sokvag] = self.g.versioner.get(sokvag, 0) + 1
            return orig(sokvag, data, ersatt, om_version)

        self.g.skriv = alltid_krock
        fore = self.g.filer[s.REGISTER_FIL]
        with self.assertRaises(s.Sparrfel) as fel:
            self.livv.register_uppdatera("LIVV-2026-0001", {"kanal": "X"})
        self.assertIn("Inget av din ändring sparades", str(fel.exception))
        self.assertEqual(self.g.filer[s.REGISTER_FIL], fore)

    def tearDown(self):
        s.Livv.FORSOK = 5


class TestGraphSkickarVersion(unittest.TestCase):
    def test_if_match_och_412(self):
        class Svar:
            def __init__(self, kod):
                self.status_code = kod

            def json(self):
                return {}

            def raise_for_status(self):
                pass

        g = s.Graph.__new__(s.Graph)
        anrop = []
        g._anrop = lambda metod, url, **kw: anrop.append(kw) or Svar(412)
        with self.assertRaises(s.Skrivkrock):
            g.skriv(s.REGISTER_FIL, b"x", ersatt=True, om_version='"{abc},3"')
        self.assertEqual(anrop[0]["headers"], {"If-Match": '"{abc},3"'})


if __name__ == "__main__":
    unittest.main()
