# Ändringslista för Innehallsregister.xlsx

Status: **genomförd 17 november 2026.** Godkänd av Mattias och genomförd med `verktyg/excel_andringar.py`. Alla 21 ändringar är gjorda och kontrollerade, rullistorna för ansvarig_agent och kanal är utökade, och ändringen är loggad i 09_Loggar. Översättningen i livv-grund är borttagen.

Kontrollerad 23 november 2026 mot en färsk kopia från SharePoint: Statusflode, Kolumner och Listor stämmer med listan nedan, rullistan för kanal når X och rullistan för ansvarig_agent når Mattias. Rullistorna ligger nu som x14-tillägg och överlever en skrivning via MCP-servern.

Bakgrund: bladen använder den äldre numreringen, där A1 och A2 skrev utkast och A7 arkiverade. Rolltabellen A0 till A8 i arbetsdokumentet gäller nu.

## Blad Statusflode
| Rad | Kolumn | Nu | Föreslaget |
|---|---|---|---|
| Utkast | Vem flyttar dit | A1/A2 | A4 |
| (A3: Revidera) | Krav | Tillbaka till A1/A2 med konkreta ändringar. Max 2 varv, därefter Eskalera. | Tillbaka till A4 med konkreta ändringar. Max 2 varv, därefter Eskalera. |
| Schemalagd | Vem flyttar dit | Claude in Chrome efter schemaläggning i LinkedIn | A0 efter att Mattias schemalagt och bekräftat |
| Schemalagd | Krav | Krav enligt livv-grund, avsnitt Publicering. Bara Livv.se. Aldrig Post now. | Mattias har schemalagt från rätt företagssida och bekräftat. planerad_publicering ifyllt. |
| Publicerad | Vem flyttar dit | Claude in Chrome efter publiceringstiden, eller Mattias | A0 efter Mattias bekräftelse |
| Arkiverad | Vem flyttar dit | A7, 30 dagar efter publicering | A2 (A0 i fas 1), 30 dagar efter publicering |
| Fas 3 | (rad) | Publicering via API och n8n ersätter Claude in Chrome | Stryks. Publicering görs av en människa. |

## Blad Kolumner, kolumnen "Fylls i av"
| Kolumn | Nu | Föreslaget |
|---|---|---|
| ansvarig_agent, exempel | A1 | A4 |
| filnamn | A1/A2 | A4 |
| version | A1/A2 | A4 |
| kallor | A1 | A4 |
| eskalera | A1/A3 | A4/A3 |
| eskalera_skal | A1/A3 | A4/A3 |
| sakerhet | A1/A3 | A4/A3 |
| publicerad_datum, plattforms_id, url | Mattias | Mattias (A0 för in uppgifterna efter hans bekräftelse) |
| resultat_30d | A7 | A2 (Mattias manuellt i fas 1) |

## Blad Listor (dolt)
| Lista | Ändring |
|---|---|
| ansvarig_agent | Lägg till A8 och Mattias. |
| kanal | Lägg till X (beslut 17 november 2026). |

Rullistor och namngivna områden som pekar på listorna utökas så att de nya värdena kommer med.

## Så genomförs ändringen
1. Mattias godkänner listan, helt eller rad för rad. Gjort 17 november 2026.
2. Mattias kör engångsverktyget `verktyg/excel_andringar.py` i en vanlig terminal, inte via en agent. Först utan flaggor (torrkörning), sedan med `--genomfor`. Verktyget läser filen direkt före ändringen och ändrar bara de celler som står här. Alla blad, rullistor och kolumnnamn behålls. En kopia av filen sparas i `.arbetsyta/` före ändringen.
3. Verktyget läser tillbaka filen och kontrollerar den. Ändringen loggas i 09_Loggar.
4. Avsnittet "Numrering i Excel-bladen" i livv-grund tas bort i en egen commit.

Verktyget ändrar en cell bara om exakt en cell matchar. Finns ingen eller flera stoppar det utan att skriva något.

---

# Förslag 2: språk (inte genomfört)

Status: **förslag, väntar på Mattias godkännande.** Bakgrund: allt som publiceras skrivs på engelska (beslut 5 november 2026, regel 2 i livv-skrivregler). Alla rader i registret har redan sprak en.

| Blad | Var | Nu | Föreslaget |
|---|---|---|---|
| Listor | kolumnen sprak | sv, en, da | en |
| Kolumner | sprak, Beskrivning | sv, en eller da | en. Allt som publiceras är på engelska |
| Kolumner | sprak, Exempel | sv | en |

Rullistan för sprak (G2:G2000) ska då peka på Listor!$E$2:$E$2. Engångsverktyget kan i dag bara ändra celler och lägga till listvärden, inte ta bort dem. Enklast är att Mattias gör ändringen för hand i Excel online och loggar den.
