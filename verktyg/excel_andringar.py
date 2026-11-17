"""Engångsverktyg: genomför docs/excel-andringslista.md i Innehallsregister.xlsx.

Mattias kör verktyget själv i en vanlig terminal, inte via en agent.

    python3 verktyg/excel_andringar.py              torrkörning: visar vad som skulle ändras
    python3 verktyg/excel_andringar.py --genomfor   gör ändringarna

Så arbetar verktyget:
- Det ändrar bara de celler som står i ändringslistan, i bladen Statusflode,
  Kolumner och Listor. Allt annat i arbetsboken kopieras oförändrat, på samma
  sätt som SharePoint-servern skriver registret.
- En cell ändras bara om exakt en cell matchar. Annars stoppar verktyget utan
  att skriva något, och säger vilken ändring som inte gick att placera.
- Före skrivning sparas en kopia av registret i .arbetsyta/. Efter skrivning
  läses filen tillbaka och kontrolleras, och ändringen loggas i 09_Loggar.
- Ändringar som redan är gjorda hoppas över, så verktyget kan köras igen.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "mcp"))

import sharepoint_server as sp  # noqa: E402


@dataclass(frozen=True)
class Andring:
    blad: str
    rad: str        # en cell i raden har exakt den här texten, eller (om rad_innehaller) innehåller den
    gammal: str     # cellen som ändras har exakt den här texten, eller (om innehaller) innehåller den
    ny: str
    innehaller: bool = False
    rad_innehaller: bool = False


ANDRINGAR = [
    # Blad Statusflode
    Andring("Statusflode", "Utkast", "A1/A2", "A4", innehaller=True),
    Andring("Statusflode", "Revidera", "Tillbaka till A1/A2",
            "Tillbaka till A4 med konkreta ändringar. Max 2 varv, därefter Eskalera.",
            innehaller=True, rad_innehaller=True),
    Andring("Statusflode", "Schemalagd", "Claude in Chrome",
            "A0 efter att Mattias schemalagt och bekräftat", innehaller=True),
    Andring("Statusflode", "Schemalagd", "Aldrig Post now",
            "Mattias har schemalagt från rätt företagssida och bekräftat. planerad_publicering ifyllt.",
            innehaller=True),
    Andring("Statusflode", "Publicerad", "Claude in Chrome", "A0 efter Mattias bekräftelse", innehaller=True),
    Andring("Statusflode", "Arkiverad", "A7", "A2 (A0 i fas 1), 30 dagar efter publicering", innehaller=True),
    Andring("Statusflode", "Fas 3", "n8n",
            "Struken 17 november 2026. Publicering görs av en människa.",
            innehaller=True, rad_innehaller=True),
    # Blad Kolumner, kolumnen "Fylls i av"
    Andring("Kolumner", "ansvarig_agent", "A1", "A4"),
    Andring("Kolumner", "filnamn", "A1/A2", "A4"),
    Andring("Kolumner", "version", "A1/A2", "A4"),
    Andring("Kolumner", "kallor", "A1", "A4"),
    Andring("Kolumner", "eskalera", "A1/A3", "A4/A3"),
    Andring("Kolumner", "eskalera_skal", "A1/A3", "A4/A3"),
    Andring("Kolumner", "sakerhet", "A1/A3", "A4/A3"),
    Andring("Kolumner", "publicerad_datum", "Mattias", "Mattias (A0 för in uppgifterna efter hans bekräftelse)"),
    Andring("Kolumner", "plattforms_id", "Mattias", "Mattias (A0 för in uppgifterna efter hans bekräftelse)"),
    Andring("Kolumner", "url", "Mattias", "Mattias (A0 för in uppgifterna efter hans bekräftelse)"),
    Andring("Kolumner", "resultat_30d", "A7", "A2 (Mattias manuellt i fas 1)"),
]

# Blad Listor: värden som ska finnas i en lista. Kolumnen hittas på rubriken i rad 1.
LISTTILLAGG = {
    "ansvarig_agent": ["A8", "Mattias"],
    "kanal": ["X"],
}


class Avbrott(Exception):
    pass


def _text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _blad(data: bytes, namn: str):
    from openpyxl import load_workbook

    bok = load_workbook(io.BytesIO(data))
    if namn not in bok.sheetnames:
        raise Avbrott(f"Bladet {namn} finns inte i registret.")
    return bok[namn]


@dataclass
class Plan:
    celler: list[tuple[Andring, int, int, str]]     # ändring, rad, kolumn, nuvarande text
    redan: list[Andring]
    fel: list[str]
    listor: list[tuple[str, str, int, int, str]]    # rubrik, kolumnbokstav, sista rad före, ny rad, värde
    listor_redan: list[tuple[str, str]]


def planera(data: bytes) -> Plan:
    from openpyxl.utils import get_column_letter

    plan = Plan([], [], [], [], [])
    for a in ANDRINGAR:
        blad = _blad(data, a.blad)
        traffar, redan = [], False
        for rad in blad.iter_rows():
            texter = [_text(c.value) for c in rad]
            if a.rad_innehaller:
                radmatch = any(a.rad in t for t in texter)
            else:
                radmatch = a.rad in texter
            if not radmatch:
                continue
            for c in rad:
                t = _text(c.value)
                if t == a.ny:
                    redan = True
                elif (a.gammal in t) if a.innehaller else (t == a.gammal):
                    traffar.append((c.row, c.column, t))
        if len(traffar) == 1:
            plan.celler.append((a, *traffar[0]))
        elif not traffar and redan:
            plan.redan.append(a)
        elif not traffar:
            plan.fel.append(f"{a.blad}, rad {a.rad}: hittar ingen cell med {a.gammal!r}.")
        else:
            platser = ", ".join(f"{get_column_letter(k)}{r}" for r, k, _ in traffar)
            plan.fel.append(f"{a.blad}, rad {a.rad}: {a.gammal!r} finns i flera celler ({platser}). Ändras inte.")

    listor = _blad(data, "Listor")
    rubriker = {_text(c.value): c.column for c in listor[1] if _text(c.value)}
    for rubrik, varden in LISTTILLAGG.items():
        if rubrik not in rubriker:
            plan.fel.append(f"Listor: hittar ingen kolumn med rubriken {rubrik!r}.")
            continue
        kol = rubriker[rubrik]
        befintliga = [(r, _text(listor.cell(r, kol).value)) for r in range(2, listor.max_row + 1)]
        sista = max([r for r, t in befintliga if t] or [1])
        finns = {t for _, t in befintliga if t}
        nasta = sista
        for v in varden:
            if v in finns:
                plan.listor_redan.append((rubrik, v))
            else:
                nasta += 1
                plan.listor.append((rubrik, get_column_letter(kol), sista, nasta, v))
    return plan


def _utoka_listomraden(data: bytes, kolumn: str, sista_fore: int, sista_efter: int) -> tuple[bytes, int]:
    """Utökar formler som pekar på Listor!$K$2:$K$<sista_fore> så att de når <sista_efter>.

    Det gäller rullistor (dataValidation, även x14-tillägg) och namngivna områden.
    Bara slutraden byts. Allt annat i filen kopieras byte för byte.
    """
    monster = re.compile(r"((?:'Listor'|Listor)!\$?" + kolumn + r"\$?\d+:\$?" + kolumn + r"\$?)(\d+)\b")
    antal = 0

    def byt(m: re.Match) -> str:
        nonlocal antal
        if int(m[2]) != sista_fore:
            return m[0]
        antal += 1
        return m[1] + str(sista_efter)

    zin = zipfile.ZipFile(io.BytesIO(data))
    ut = io.BytesIO()
    with zipfile.ZipFile(ut, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            innehall = zin.read(info.filename)
            if info.filename.endswith(".xml") and info.filename.startswith(("xl/worksheets/", "xl/workbook")):
                text = innehall.decode("utf-8")
                ny = monster.sub(byt, text)
                if ny != text:
                    innehall = ny.encode("utf-8")
            zout.writestr(info, innehall)
    return ut.getvalue(), antal


def tillampa(data: bytes, plan: Plan) -> tuple[bytes, list[str]]:
    if plan.fel:
        raise Avbrott("Planen har fel. Inget ändras.")
    rapport = []
    for a, rad, kol, _ in plan.celler:
        data = sp.skriv_celler(data, a.blad, rad, {kol: a.ny})
    from openpyxl.utils import column_index_from_string

    per_kolumn: dict[str, list[tuple[str, int, int, str]]] = {}
    for rubrik, bokstav, sista, ny_rad, varde in plan.listor:
        per_kolumn.setdefault(bokstav, []).append((rubrik, sista, ny_rad, varde))
    for bokstav, poster in per_kolumn.items():
        sista_fore = poster[0][1]
        for rubrik, sista, ny_rad, varde in poster:
            data = sp.skriv_celler(data, "Listor", ny_rad, {column_index_from_string(bokstav): varde}, sista)
        sista_efter = poster[-1][2]
        data, antal = _utoka_listomraden(data, bokstav, sista_fore, sista_efter)
        rapport.append(f"Listor, {poster[0][0]}: {antal} rullista(or) eller namngivna områden utökade till rad {sista_efter}.")
    return data, rapport


def kontrollera(data: bytes, plan: Plan) -> None:
    for a, rad, kol, _ in plan.celler:
        varde = _text(_blad(data, a.blad).cell(rad, kol).value)
        if varde != a.ny:
            raise Avbrott(f"Kontrollen misslyckades: {a.blad} rad {rad} har {varde!r}.")
    listor = _blad(data, "Listor")
    from openpyxl.utils import column_index_from_string

    for _, bokstav, _, ny_rad, varde in plan.listor:
        if _text(listor.cell(ny_rad, column_index_from_string(bokstav)).value) != varde:
            raise Avbrott(f"Kontrollen misslyckades: Listor {bokstav}{ny_rad} saknar {varde!r}.")


def skriv_ut(plan: Plan) -> None:
    from openpyxl.utils import get_column_letter

    print("Ändringar som görs:")
    for a, rad, kol, nu in plan.celler:
        print(f"  {a.blad} {get_column_letter(kol)}{rad}: {nu!r}\n      blir {a.ny!r}")
    for rubrik, bokstav, _, ny_rad, varde in plan.listor:
        print(f"  Listor {bokstav}{ny_rad}: lägg till {varde!r} i {rubrik}")
    if not plan.celler and not plan.listor:
        print("  Inga.")
    if plan.redan or plan.listor_redan:
        print("Redan gjort:")
        for a in plan.redan:
            print(f"  {a.blad}, rad {a.rad}")
        for rubrik, v in plan.listor_redan:
            print(f"  Listor, {rubrik}: {v}")
    if plan.fel:
        print("Kan inte placeras, inget ändras förrän det är löst:")
        for f in plan.fel:
            print(f"  {f}")


def main(argv: list[str]) -> int:
    genomfor = "--genomfor" in argv
    graph = sp.Graph()
    data = graph.las(sp.REGISTER_FIL)
    plan = planera(data)
    skriv_ut(plan)
    if plan.fel:
        print("\nStoppat. Skicka den här utskriften till Claude.")
        return 1
    if not plan.celler and not plan.listor:
        print("\nAllt är redan gjort.")
        return 0
    if not genomfor:
        print("\nTorrkörning: inget är ändrat. Kör igen med --genomfor för att ändra.")
        return 0

    data = graph.las(sp.REGISTER_FIL)  # läs direkt före ändringen
    plan = planera(data)
    if plan.fel:
        skriv_ut(plan)
        print("\nRegistret ändrades under tiden. Stoppat.")
        return 1
    kopia = ROT / ".arbetsyta" / f"Innehallsregister_fore_andring_{datetime.now():%Y%m%d_%H%M}.xlsx"
    kopia.parent.mkdir(exist_ok=True)
    kopia.write_bytes(data)
    print(f"\nKopia före ändringen: {kopia}")

    nytt, rapport = tillampa(data, plan)
    graph.skriv(sp.REGISTER_FIL, nytt, ersatt=True)
    kontrollera(graph.las(sp.REGISTER_FIL), plan)
    for rad in rapport:
        print(rad)
    sp.Livv(graph).logga("Mattias", "", "Ändrade Statusflode, Kolumner och Listor enligt ändringslistan",
                         sp.REGISTER_FIL, f"{len(plan.celler)} celler, {len(plan.listor)} listvärden")
    print("Klart. Registret är ändrat, kontrollerat och loggat.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (Avbrott, sp.Sparrfel) as fel:
        print(f"Stoppat: {fel}")
        sys.exit(1)
