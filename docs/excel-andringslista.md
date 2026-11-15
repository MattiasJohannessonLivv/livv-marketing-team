# Ändringslista för Innehallsregister.xlsx

Status: **förslag, inte genomfört.** Körs först när Mattias godkänt listan, efter torrtestet. Fram till dess gäller översättningen i avsnittet "Numrering i Excel-bladen" i livv-grund.

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

## Så genomförs ändringen
1. Mattias godkänner listan, helt eller rad för rad.
2. A0 läser filen direkt före ändringen och ändrar bara de celler som står här. Alla blad, rullistor och kolumnnamn behålls.
3. Filen läses tillbaka och kontrolleras. Ändringen loggas i 09_Loggar.
4. Avsnittet "Numrering i Excel-bladen" i livv-grund tas bort i en egen commit.

Obs: MCP-servern har i dag inget verktyg som skriver i bladen Statusflode, Kolumner eller Listor. Ändringen görs därför av Mattias i Excel, eller med ett engångsverktyg som byggs och granskas separat.
