"""Tester för engångsverktyget verktyg/excel_andringar.py, utan nätverk."""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "verktyg"))
sys.path.insert(0, str(ROT / "mcp"))

import excel_andringar as ea  # noqa: E402


def gammalt_register() -> bytes:
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    bok = Workbook()
    reg = bok.active
    reg.title = "Register"
    reg.append(["objekt_id", "kanal", "ansvarig_agent"])
    reg.append(["LIVV-2026-0001", "LinkedIn", "A0"])
    dv = DataValidation(type="list", formula1="Listor!$B$2:$B$9", allow_blank=True)
    dv.add("C2:C500")
    reg.add_data_validation(dv)
    dv2 = DataValidation(type="list", formula1="Listor!$A$2:$A$4", allow_blank=True)
    dv2.add("B2:B500")
    reg.add_data_validation(dv2)

    sf = bok.create_sheet("Statusflode")
    sf.append(["Status", "Mapp", "Vem flyttar dit", "Krav"])
    sf.append(["Brief", "01_Briefer", "A0", "Brief komplett"])
    sf.append(["Utkast", "02_Utkast", "A1/A2", "Utkast sparat"])
    sf.append(["(A3: Revidera)", "", "A3", "Tillbaka till A1/A2 med konkreta ändringar. Max 2 varv, därefter Eskalera."])
    sf.append(["Schemalagd", "04_Godkant", "Claude in Chrome efter schemaläggning i LinkedIn",
               "Krav enligt livv-grund, avsnitt Publicering. Bara Livv.se. Aldrig Post now."])
    sf.append(["Publicerad", "05_Publicerat", "Claude in Chrome efter publiceringstiden, eller Mattias", ""])
    sf.append(["Arkiverad", "06_Arkiv", "A7, 30 dagar efter publicering", "resultat_30d ifyllt"])
    sf.append(["Fas 3", "", "", "Publicering via API och n8n ersätter Claude in Chrome"])

    ko = bok.create_sheet("Kolumner")
    ko.append(["Kolumn", "Beskrivning", "Fylls i av", "Exempel"])
    for namn, vem in [("ansvarig_agent", "A1"), ("filnamn", "A1/A2"), ("version", "A1/A2"), ("kallor", "A1"),
                      ("eskalera", "A1/A3"), ("eskalera_skal", "A1/A3"), ("sakerhet", "A1/A3"),
                      ("publicerad_datum", "Mattias"), ("plattforms_id", "Mattias"), ("url", "Mattias"),
                      ("resultat_30d", "A7")]:
        ko.append([namn, "", vem, ""])

    li = bok.create_sheet("Listor")
    li.sheet_state = "hidden"
    li.append(["kanal", "ansvarig_agent"])
    for i, (k, a) in enumerate([("LinkedIn", "A0"), ("Meta", "A1"), ("Google", "A2")]):
        li.append([k, a])
    for a in ["A3", "A4", "A5", "A6", "A7"]:
        li.append([None, a])
    buf = io.BytesIO()
    bok.save(buf)
    return buf.getvalue()


class TestExcelAndringar(unittest.TestCase):
    def test_torrkorning_hittar_allt(self):
        plan = ea.planera(gammalt_register())
        self.assertEqual(plan.fel, [])
        self.assertEqual(len(plan.celler), len(ea.ANDRINGAR))
        self.assertEqual([(r, v) for r, _, _, _, v in plan.listor],
                         [("ansvarig_agent", "A8"), ("ansvarig_agent", "Mattias"), ("kanal", "X")])

    def test_genomfor_och_kontrollera(self):
        data = gammalt_register()
        plan = ea.planera(data)
        nytt, rapport = ea.tillampa(data, plan)
        ea.kontrollera(nytt, plan)
        ko = ea._blad(nytt, "Kolumner")
        self.assertEqual(ko["C2"].value, "A4")
        self.assertEqual(ko["C12"].value, "A2 (Mattias manuellt i fas 1)")
        sf = ea._blad(nytt, "Statusflode")
        self.assertEqual(sf["C3"].value, "A4")
        self.assertEqual(sf["D3"].value, "Utkast sparat")
        self.assertTrue(sf["D8"].value.startswith("Struken"))
        li = ea._blad(nytt, "Listor")
        self.assertEqual((li["B10"].value, li["B11"].value, li["A5"].value), ("A8", "Mattias", "X"))
        self.assertEqual(li.sheet_state, "hidden")
        # Rullistorna pekar nu på de utökade områdena
        reg = zipfile.ZipFile(io.BytesIO(nytt)).read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Listor!$B$2:$B$11", reg)
        self.assertIn("Listor!$A$2:$A$5", reg)
        self.assertEqual(len(rapport), 2)

    def test_andra_korningen_gor_inget(self):
        data = gammalt_register()
        nytt, _ = ea.tillampa(data, ea.planera(data))
        plan = ea.planera(nytt)
        self.assertEqual((plan.celler, plan.listor, plan.fel), ([], [], []))
        self.assertEqual(len(plan.redan), len(ea.ANDRINGAR))

    def test_tvetydig_cell_stoppar_allt(self):
        from openpyxl import load_workbook

        bok = load_workbook(io.BytesIO(gammalt_register()))
        bok["Statusflode"]["D3"] = "A1/A2 skriver utkast"
        buf = io.BytesIO()
        bok.save(buf)
        plan = ea.planera(buf.getvalue())
        self.assertEqual(len(plan.fel), 1)
        self.assertIn("flera celler", plan.fel[0])
        with self.assertRaises(ea.Avbrott):
            ea.tillampa(buf.getvalue(), plan)

    def test_ovriga_blad_och_celler_orora(self):
        data = gammalt_register()
        nytt, _ = ea.tillampa(data, ea.planera(data))
        fore, efter = zipfile.ZipFile(io.BytesIO(data)), zipfile.ZipFile(io.BytesIO(nytt))
        self.assertEqual(fore.namelist(), efter.namelist())
        reg_fore = ea._blad(data, "Register")
        reg_efter = ea._blad(nytt, "Register")
        self.assertEqual([[c.value for c in r] for r in reg_fore.iter_rows()],
                         [[c.value for c in r] for r in reg_efter.iter_rows()])


if __name__ == "__main__":
    unittest.main()
