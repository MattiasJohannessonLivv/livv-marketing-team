"""Tester för teamtavlan, utan nätverk.

Kör: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "tavla"))
sys.path.insert(0, str(ROT / "mcp"))

import server as tavla  # noqa: E402
import sharepoint_server as sp  # noqa: E402
from test_sokvagar import testregister  # noqa: E402


def loggbok(rader: list[list]) -> bytes:
    from openpyxl import load_workbook

    bok = load_workbook(io.BytesIO(sp.logg_ny_bok()))
    for rad in rader:
        bok.active.append(rad)
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


class FalskGraph:
    """Läsande attrapp. Registrerar varje anrop så att testerna kan se att inget skrivs."""

    def __init__(self, filer: dict[str, bytes]) -> None:
        self.filer = filer
        self.anrop: list[str] = []

    def las(self, sokvag: str) -> bytes:
        self.anrop.append("las " + sokvag)
        return self.filer[sokvag]

    def finns(self, sokvag: str) -> bool:
        self.anrop.append("finns " + sokvag)
        return sokvag in self.filer


class TestOmvandling(unittest.TestCase):
    def test_registerrad_blir_objekt(self):
        rad = {
            "objekt_id": "LIVV-2026-0002", "varumarke": "Livv Group", "kanal": "LinkedIn", "titel": "",
            "kampanj": "Vinter", "status": "Granskning", "a3_utfall": "Godkänd", "revideringsvarv": 1,
            "planerad_publicering": datetime(2026, 11, 24, 7, 45), "senast_andrad": "2026-11-11 10:15",
            "eskalera": "Nej", "briefdatum": "2026-11-10", "godkand_datum": None,
        }
        o = tavla.objekt_fran_register([rad, {"objekt_id": ""}])
        self.assertEqual(len(o), 1)
        o = o[0]
        self.assertEqual(o["bolag"], "LivvGroup")
        self.assertEqual(o["titel"], "Vinter")
        self.assertEqual(o["varv"], 1)
        self.assertEqual(o["plan"], "2026-11-24")
        self.assertEqual(o["sedan"], "2026-11-11T10:15")
        self.assertEqual(o["briefdatum"], "2026-11-10T00:00")
        self.assertEqual(o["godkand_datum"], "")
        self.assertFalse(o["eskalera"])

    def test_okant_bolag_och_eskalering(self):
        o = tavla.objekt_fran_register([{"objekt_id": "UNIQ-2026-0001", "varumarke": "Annat", "eskalera": "Ja"}])[0]
        self.assertEqual(o["bolag"], "Okand")
        self.assertTrue(o["eskalera"])
        self.assertEqual(o["titel"], "UNIQ-2026-0001")

    def test_riktigt_testregister_kan_lasas(self):
        o = tavla.objekt_fran_register(sp.register_rader(testregister()))
        self.assertEqual([x["id"] for x in o], ["LIVV-2026-0001"])

    def test_loggrader(self):
        data = loggbok([
            ["2026-11-17", "14:37", "A0", "LIVV-2026-0001", "Satte status Avvisad", "07_Avvisat/Livv", "Test"],
            [datetime(2026, 11, 16), 0.375, "Mattias", "", "Godkände", "", None],
            [None, None, None, None, None, None, None],
        ])
        rader = tavla.logg_fran_bok(data)
        self.assertEqual(rader[0], ["2026-11-17", "14:37", "A0", "LIVV-2026-0001", "Satte status Avvisad", "Test"])
        self.assertEqual(rader[1], ["2026-11-16", "09:00", "Mattias", "", "Godkände", ""])
        self.assertEqual(len(rader), 2)

    def test_svenska_och_ofullstandiga_tider(self):
        self.assertEqual(tavla._klocka("9.52"), "09:52")
        self.assertEqual(tavla._klocka("09:52:10"), "09:52")
        self.assertEqual(tavla._klocka("kl. 14.05"), "14:05")
        self.assertEqual(tavla._klocka(""), "")
        self.assertEqual(tavla._klocka("99:99"), "")
        self.assertEqual(tavla._datum("2026-11-5"), "2026-11-05")
        self.assertEqual(tavla._datum("2026-11-05 00:00:00"), "2026-11-05")
        self.assertEqual(tavla._tidpunkt("2026-11-5 9.52"), "2026-11-05T09:52")
        self.assertEqual(tavla._tidpunkt("2026-11-05"), "2026-11-05T00:00")
        self.assertEqual(tavla._tidpunkt("okänt"), "")

    def test_fel_kolumner_i_loggen_stoppas(self):
        from openpyxl import Workbook

        bok = Workbook()
        bok.active.append(["Datum", "Vem"])
        buf = io.BytesIO()
        bok.save(buf)
        with self.assertRaises(sp.Sparrfel):
            tavla.logg_fran_bok(buf.getvalue())

    def test_manader_over_arsskifte(self):
        self.assertEqual(tavla.manader(datetime(2027, 1, 3)), ["2026-12", "2027-01"])
        self.assertEqual(tavla.manader(datetime(2026, 11, 17)), ["2026-10", "2026-11"])


class TestHamta(unittest.TestCase):
    def test_hamta_laser_register_och_tva_manader(self):
        g = FalskGraph({
            sp.REGISTER_FIL: testregister(),
            "09_Loggar/Logg_2026-11.xlsx": loggbok([["2026-11-02", "08:00", "A0", "", "B", "", ""]]),
            "09_Loggar/Logg_2026-10.xlsx": loggbok([["2026-10-30", "09:00", "A4", "", "A", "", ""]]),
        })
        d = tavla.hamta(g, datetime(2026, 11, 17, 14, 40))
        self.assertEqual(d["kalla"], "sharepoint")
        self.assertEqual([r[4] for r in d["logg"]], ["A", "B"])
        self.assertEqual(len(d["objekt"]), 1)
        self.assertTrue(all(a.startswith(("las ", "finns ")) for a in g.anrop))

    def test_saknad_manad_ar_inget_fel(self):
        g = FalskGraph({sp.REGISTER_FIL: testregister()})
        d = tavla.hamta(g, datetime(2026, 11, 17))
        self.assertEqual(d["logg"], [])
        self.assertEqual(d["varningar"], [])

    def test_lasgraph_kan_inte_skriva(self):
        lg = tavla.LasGraph(FalskGraph({}))
        for namn in ("skriv", "flytta", "skapa_mapp_om_saknas", "_anrop"):
            self.assertFalse(hasattr(lg, namn), namn)


def obj(id_: str, status: str, a3: str = "", eskalera: bool = False, **extra) -> dict:
    o = {"id": id_, "titel": "T " + id_, "status": status, "a3": a3, "eskalera": eskalera, "mapp": "", "filnamn": ""}
    o.update(extra)
    return o


class TestVantarOchNotiser(unittest.TestCase):
    def test_vantande(self):
        lista = tavla.vantande([
            obj("A", "Brief"),
            obj("B", "Granskning", "Godkänd"),
            obj("C", "Utkast", "Eskalera", eskalera=True),
            obj("D", "Godkänd", "Godkänd"),
            obj("E", "Avvisad", eskalera=True),
            obj("F", "Utkast", "Revidera"),
        ])
        self.assertEqual([(o["id"], o["etikett"]) for o in lista], [("B", "Godkänn"), ("C", "Beslut"), ("D", "Publicera")])

    def test_notis_vid_start_och_bara_for_nya(self):
        skickat = []
        p = tavla.Pingare(lambda titel, text: skickat.append(text))
        p.kontrollera({"objekt": [obj("B", "Granskning", "Godkänd")]})
        self.assertEqual(skickat, ["1 sak väntar på ditt beslut."])
        p.kontrollera({"objekt": [obj("B", "Granskning", "Godkänd")]})
        self.assertEqual(len(skickat), 1)
        p.kontrollera({"objekt": [obj("B", "Godkänd"), obj("C", "Granskning", "Godkänd")]})
        self.assertEqual(skickat[1:], ["B T B", "C T C"])

    def test_ingen_notis_vid_start_om_inget_vantar(self):
        skickat = []
        p = tavla.Pingare(lambda titel, text: skickat.append(text))
        p.kontrollera({"objekt": [obj("A", "Brief")]})
        self.assertEqual(skickat, [])

    def test_notisskriptet_citerar_text(self):
        skript = tavla.notis_skript("Livv", 'Säg "hej"\nnu')
        self.assertEqual(skript, 'display notification "Säg \\"hej\\" nu" with title "Livv" sound name "Glass"')

    def test_lank_till_vantande_fil(self):
        g = FalskGraph({sp.REGISTER_FIL: testregister()})
        g.webblank = lambda sokvag: "https://exempel/" + sokvag
        objekt = [obj("B", "Granskning", "Godkänd", mapp="03_Granskning/Livv", filnamn="b.md"), obj("A", "Brief", mapp="01_Briefer/Livv", filnamn="a.md")]
        orig = tavla.objekt_fran_register
        tavla.objekt_fran_register = lambda rader: objekt
        try:
            d = tavla.hamta(g, datetime(2026, 11, 17))
        finally:
            tavla.objekt_fran_register = orig
        self.assertEqual(d["objekt"][0]["lank"], "https://exempel/03_Granskning/Livv/b.md")
        self.assertNotIn("lank", d["objekt"][1])


class TestWebbserver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {"kalla": "sharepoint", "hamtad": "2026-11-17T14:40", "objekt": [], "logg": [], "varningar": []}
        cache = tavla.Cache(lambda: cls.data)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), tavla.bygg_hanterare(cache))
        cls.bas = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def hamta(self, sokvag: str, metod: str = "GET"):
        return urllib.request.urlopen(urllib.request.Request(self.bas + sokvag, method=metod), timeout=5)

    def test_sidan_och_datan(self):
        self.assertIn(b"Teamtavla", self.hamta("/").read())
        self.assertEqual(json.loads(self.hamta("/data.json").read()), self.data)
        exempel = json.loads(self.hamta("/exempeldata.json").read())
        self.assertEqual(exempel["kalla"], "exempel")

    def test_bara_get(self):
        for metod in ("POST", "PUT", "DELETE"):
            with self.assertRaises(urllib.error.HTTPError) as fel:
                self.hamta("/data.json", metod)
            self.assertEqual(fel.exception.code, 501)

    def test_okand_sokvag(self):
        for sokvag in ("/.env", "/../.env", "/server.py"):
            with self.assertRaises(urllib.error.HTTPError) as fel:
                self.hamta(sokvag)
            self.assertEqual(fel.exception.code, 404)

    def test_server_lyssnar_bara_lokalt(self):
        self.assertEqual(tavla.VARD, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
