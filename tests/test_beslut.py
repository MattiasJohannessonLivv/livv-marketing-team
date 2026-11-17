"""Tester för Mattias beslut i teamtavlan (tavla/beslut.py och POST i servern), utan nätverk."""

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

import beslut as b  # noqa: E402
import server as tavla  # noqa: E402
import sharepoint_server as sp  # noqa: E402
from test_sokvagar import KOLUMNER  # noqa: E402

UTKAST = "20261117_livv_linkedin_q1-oppning_inlagg_v02.md"
BRIEF = "20261117_livv_linkedin_q1-oppning_brief_v01.md"


def register(rader: list[dict]) -> bytes:
    from openpyxl import Workbook

    bok = Workbook()
    blad = bok.active
    blad.title = "Register"
    blad.append(KOLUMNER)
    for r in rader:
        blad.append([r.get(k) for k in KOLUMNER])
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


class MinnesGraph:
    """Graph i minnet med samma metoder som sp.Graph använder i Livv."""

    def __init__(self, filer: dict[str, bytes]) -> None:
        self.filer = dict(filer)
        self.flyttar: list[tuple[str, str]] = []

    def las(self, sokvag):
        if sokvag not in self.filer:
            raise sp.Sparrfel(f"Hittar inte {sokvag}")
        return self.filer[sokvag]

    def finns(self, sokvag):
        return sokvag in self.filer or any(p.startswith(sokvag + "/") for p in self.filer)

    def skriv(self, sokvag, data, ersatt):
        if sokvag in self.filer and not ersatt:
            raise sp.Sparrfel("finns")
        self.filer[sokvag] = data

    def skapa_mapp_om_saknas(self, sokvag):
        pass

    def flytta(self, fran, till_mapp):
        namn = fran.rsplit("/", 1)[1]
        self.filer[f"{till_mapp}/{namn}"] = self.filer.pop(fran)
        self.flyttar.append((fran, till_mapp))

    def lista(self, sokvag):
        return [p[len(sokvag) + 1:] for p in self.filer if p.startswith(sokvag + "/") and "/" not in p[len(sokvag) + 1:]]


def grund(**rad) -> MinnesGraph:
    standard = {"objekt_id": "LIVV-2026-0002", "varumarke": "Livv", "kanal": "LinkedIn", "titel": "Kvartalets öppning",
                "status": "Granskning", "a3_utfall": "Godkänd", "sakerhet": "Hög", "eskalera": "Nej",
                "filnamn": UTKAST, "mapp": "03_Granskning/Livv"}
    standard.update(rad)
    return MinnesGraph({
        sp.REGISTER_FIL: register([standard]),
        f"03_Granskning/Livv/{UTKAST}": "Utkastets text".encode(),
        f"02_Utkast/Livv/{UTKAST}": "Utkastets text".encode(),
        f"01_Briefer/Livv/{BRIEF}": "Briefens text".encode(),
    })


class LasVy:
    """Läsande vy av samma minnesgraph, som LasGraph i servern."""

    def __init__(self, g):
        self.g = g

    def las(self, s):
        return self.g.las(s)

    def lista(self, s):
        return self.g.lista(s)


NU = lambda: datetime(2026, 11, 18, 9, 30)  # noqa: E731


class TestBeslut(unittest.TestCase):
    def test_detalj_visar_utkast_och_brief(self):
        g = grund()
        d = b.Beslut(LasVy(g), g, NU).detalj("LIVV-2026-0002")
        self.assertEqual(d["utkast"]["text"], "Utkastets text")
        self.assertEqual(d["brief"]["namn"], BRIEF)
        self.assertEqual(d["brief"]["text"], "Briefens text")
        self.assertEqual((d["a3"], d["sakerhet"]), ("Godkänd", "Hög"))

    def test_godkann_flyttar_uppdaterar_och_loggar(self):
        g = grund()
        text = b.Beslut(LasVy(g), g, NU).godkann("LIVV-2026-0002")
        self.assertIn("godkänd", text)
        self.assertIn(f"04_Godkant/Livv/{UTKAST}", g.filer)
        rad = sp.register_rader(g.filer[sp.REGISTER_FIL], "LIVV-2026-0002")[0]
        self.assertEqual((rad["status"], rad["mapp"], rad["godkand_av"], rad["godkand_datum"]),
                         ("Godkänd", "04_Godkant/Livv", "Mattias", "2026-11-18"))
        logg = [p for p in g.filer if p.startswith("09_Loggar/")]
        self.assertEqual(len(logg), 1)
        from openpyxl import load_workbook
        rader = [list(r) for r in load_workbook(io.BytesIO(g.filer[logg[0]])).active.iter_rows(values_only=True)]
        self.assertTrue(any(r[2] == "Mattias" and r[4] == "Godkände i teamtavlan" for r in rader))

    def test_godkann_kraver_a3_och_granskning(self):
        for rad in ({"status": "Utkast"}, {"a3_utfall": "Revidera"}, {"eskalera": "Ja"}):
            g = grund(**rad)
            with self.assertRaises(sp.Sparrfel):
                b.Beslut(LasVy(g), g, NU).godkann("LIVV-2026-0002")
            self.assertEqual(g.flyttar, [], rad)

    def test_ogiltigt_id(self):
        g = grund()
        for objekt_id in ("", "../x", "LIVV-2026-9999"):
            with self.assertRaises(sp.Sparrfel):
                b.Beslut(LasVy(g), g, NU).godkann(objekt_id)

    def test_skicka_tillbaka(self):
        g = grund()
        b.Beslut(LasVy(g), g, NU).tillbaka("LIVV-2026-0002", "Kortare inledning, \n och  tydligare CTA.")
        self.assertIn(f"02_Utkast/Livv/{UTKAST}", g.filer)
        rad = sp.register_rader(g.filer[sp.REGISTER_FIL], "LIVV-2026-0002")[0]
        self.assertEqual((rad["status"], rad["a3_utfall"]), ("Utkast", "Revidera"))
        self.assertEqual(rad["godkand_av"], "")

    def test_skicka_tillbaka_kraver_kommentar(self):
        g = grund()
        with self.assertRaises(sp.Sparrfel):
            b.Beslut(LasVy(g), g, NU).tillbaka("LIVV-2026-0002", "   ")

    def test_eskalerat_utkast_tillbaka(self):
        g = grund(status="Utkast", a3_utfall="Eskalera", eskalera="Ja", mapp="02_Utkast/Livv")
        b.Beslut(LasVy(g), g, NU).tillbaka("LIVV-2026-0002", "Ta bort kundnamnet.")
        rad = sp.register_rader(g.filer[sp.REGISTER_FIL], "LIVV-2026-0002")[0]
        self.assertEqual((rad["status"], rad["eskalera"], rad["a3_utfall"]), ("Utkast", "Nej", "Revidera"))
        self.assertEqual(g.flyttar, [])


PNG = b"\x89PNG\r\n\x1a\nfake"


class TestBilder(unittest.TestCase):
    def godkand(self, **extra) -> MinnesGraph:
        g = grund(status="Godkänd", mapp="04_Godkant/Livv", **extra)
        g.filer["12_Pictures/.mapp"] = b""
        return g

    def test_bildbrief_bara_efter_godkand_text(self):
        g = grund()  # status Granskning
        g.filer["12_Pictures/.mapp"] = b""
        with self.assertRaises(sp.Sparrfel):
            sp.Livv(g).spara_bildbrief("LIVV-2026-0002", "# Image brief")
        g = self.godkand()
        forsta = sp.Livv(g).spara_bildbrief("LIVV-2026-0002", "# Image brief")
        andra = sp.Livv(g).spara_bildbrief("LIVV-2026-0002", "# Image brief v2")
        self.assertEqual(forsta, "12_Pictures/LIVV-2026-0002/LIVV-2026-0002_image-brief_v01.md")
        self.assertEqual(andra, "12_Pictures/LIVV-2026-0002/LIVV-2026-0002_image-brief_v02.md")
        self.assertEqual(g.filer[forsta], b"# Image brief")

    def test_bildbrief_kraver_mappen(self):
        g = grund(status="Godkänd")
        with self.assertRaises(sp.Sparrfel) as fel:
            sp.Livv(g).spara_bildbrief("LIVV-2026-0002", "# Image brief")
        self.assertIn("12_Pictures", str(fel.exception))

    def test_bildforslag_och_val(self):
        g = self.godkand()
        g.filer["12_Pictures/LIVV-2026-0002/LIVV-2026-0002_image-brief_v01.md"] = b"x"
        g.filer["12_Pictures/LIVV-2026-0002/forslag-b.jpg"] = PNG
        g.filer["12_Pictures/LIVV-2026-0002/forslag-a.png"] = PNG
        beslut = b.Beslut(LasVy(g), g, NU)
        self.assertEqual(beslut.bilder("LIVV-2026-0002"), ["forslag-a.png", "forslag-b.jpg"])
        self.assertEqual(beslut.bild("LIVV-2026-0002", "forslag-a.png"), PNG)
        for fel_namn in ("../../Innehallsregister.xlsx", "LIVV-2026-0002_image-brief_v01.md", "saknas.png"):
            with self.assertRaises(sp.Sparrfel):
                beslut.bild("LIVV-2026-0002", fel_namn)
        self.assertIn("vald", beslut.valj_bild("LIVV-2026-0002", "forslag-b.jpg"))
        from openpyxl import load_workbook
        logg = next(p for p in g.filer if p.startswith("09_Loggar/"))
        rader = [list(r) for r in load_workbook(io.BytesIO(g.filer[logg])).active.iter_rows(values_only=True)]
        self.assertTrue(any(r[4] == "Valde bild i teamtavlan" and r[6] == "forslag-b.jpg" for r in rader))

    def test_bild_valjs_inte_fore_godkand_text(self):
        g = grund()
        g.filer["12_Pictures/LIVV-2026-0002/a.png"] = PNG
        with self.assertRaises(sp.Sparrfel):
            b.Beslut(LasVy(g), g, NU).valj_bild("LIVV-2026-0002", "a.png")

    def test_tavlan_visar_valj_bild_och_sedan_publicera(self):
        g = self.godkand()
        g.filer["12_Pictures/LIVV-2026-0002/a.png"] = PNG
        g.objekt = lambda s: {"webUrl": ""}
        las = tavla.LasGraph(g)
        g_lista = MinnesGraph.lista
        g.lista = lambda s: [{"name": n} for n in g_lista(g, s)]
        d = tavla.hamta(las, datetime(2026, 11, 18))
        o = d["objekt"][0]
        self.assertEqual((o["bilder"], o["bild_vald"]), (["a.png"], ""))
        self.assertEqual(tavla.vantande(d["objekt"])[0]["etikett"], "Välj bild")
        b.Beslut(las, g, NU).valj_bild("LIVV-2026-0002", "a.png")
        d = tavla.hamta(las, datetime(2026, 11, 18))
        self.assertEqual(d["objekt"][0]["bild_vald"], "a.png")
        self.assertEqual(tavla.vantande(d["objekt"])[0]["etikett"], "Publicera")


class TestRiktigLasvag(unittest.TestCase):
    def test_brief_hittas_via_lasgraph(self):
        g = grund()
        riktig = MinnesGraph.lista
        g.lista = lambda s: [{"name": n} for n in riktig(g, s)]  # sp.Graph.lista ger poster med name
        d = b.Beslut(tavla.LasGraph(g), g, NU).detalj("LIVV-2026-0002")
        self.assertEqual(d["brief"]["namn"], BRIEF)


class TestSkydd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = grund()
        cls.cache = tavla.Cache(lambda: {"objekt": [], "logg": []})
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                         tavla.bygg_hanterare(cls.cache, b.Beslut(LasVy(cls.g), cls.g, NU), "hemlig"))
        cls.port = cls.server.server_address[1]
        cls.bas = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, sokvag, data, **huvuden):
        h = {"Content-Type": "application/json", "X-Tavla-Nyckel": "hemlig"}
        h.update(huvuden)
        h = {k: v for k, v in h.items() if v is not None}
        req = urllib.request.Request(self.bas + sokvag, data=json.dumps(data).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as svar:
                return svar.status, json.loads(svar.read())
        except urllib.error.HTTPError as fel:
            return fel.code, json.loads(fel.read() or b"{}")

    def test_nyckeln_finns_bara_i_sidan(self):
        sida = urllib.request.urlopen(self.bas + "/", timeout=5).read().decode()
        self.assertIn('"hemlig"', sida)
        self.assertNotIn(tavla.NYCKEL_PLATS, sida)

    def test_stoppar_utan_nyckel_fel_ursprung_eller_typ(self):
        fore = len(self.g.flyttar)
        for huvuden in ({"X-Tavla-Nyckel": None}, {"X-Tavla-Nyckel": "fel"}, {"Origin": "https://ond.example"},
                        {"Content-Type": "text/plain"}, {"Host": "ond.example"}):
            kod, _ = self.post("/godkann", {"id": "LIVV-2026-0002"}, **huvuden)
            self.assertEqual(kod, 403, huvuden)
        self.assertEqual(len(self.g.flyttar), fore)

    def test_get_med_fel_vard_stoppas(self):
        req = urllib.request.Request(self.bas + "/data.json", headers={"Host": "ond.example:80"})
        with self.assertRaises(urllib.error.HTTPError) as fel:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(fel.exception.code, 403)

    def test_objekt_och_godkann_via_servern(self):
        d = json.loads(urllib.request.urlopen(self.bas + "/objekt?id=LIVV-2026-0002", timeout=5).read())
        self.assertEqual(d["utkast"]["text"], "Utkastets text")
        kod, svar = self.post("/godkann", {"id": "LIVV-2026-0002"}, Origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual((kod, svar.get("ok")), (200, True))
        kod, svar = self.post("/godkann", {"id": "LIVV-2026-0002"})
        self.assertEqual(kod, 502)
        self.assertIn("Granskning", svar["fel"])


if __name__ == "__main__":
    unittest.main()
