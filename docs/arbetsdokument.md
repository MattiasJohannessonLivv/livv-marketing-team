# Livv Group AI-marknadsteam: arbetsdokument

Nov 15, 2026 · Mattias Johannesson

> Överfört ordagrant från PDF-versionen av arbetsdokumentet. Diagrammen i PDF:en är återgivna som text.

## Syfte och omfattning

Livv Group bygger ett AI-marknadsteam med nio agenter, A0 till A8, som arbetar i en sluten loop: insikt, plan, produktion, granskning, godkännande, publicering, mätning och lärande. Teamet byggs i Claude Code ovanpå den befintliga grunden Livv Marketing Ops i SharePoint och omfattar varumärkena Livv Group, Livv och Unique.

Två principer styr allt. Mattias godkänner varje objekt innan det når 04_Godkant. Ingen agent publicerar eller ändrar budgetar, bud eller kampanjer.

Claude är teamets hjärna och arbetsyta. Grok används där realtidsbevakning av nätet och X ger mest värde.

## Teamet: nio roller

A3 behålls som egen granskare, så den som beställer ett material aldrig godkänner det själv. Numreringen nedan är ett förslag. Grunden listar i dag A0 till A7, så A8 måste läggas till i livv-grund.

| Agent | Roll | Motor | Ansvar | Viktigaste kopplingar |
|---|---|---|---|---|
| A0 | Marketing Director | Claude | Prioriterar, sätter veckoplan, skapar objekt och briefer, fördelar jobb, rapporterar till Mattias | Innehallsregister, 01_Briefer, insiktsmapp, 09_Loggar |
| A1 | Trendspotter | Grok | Daglig omvärldsbevakning inom hotell, spa och hospitality, rapporterar trender som idéunderlag | xAI API med webb- och X-sökning, Meta Ad Library |
| A2 | Researcher | Claude | Analyserar resultat, skriver lärdomar per objekt och kanal, föreslår nästa steg | Matregister, Data Core, GA4, Search Console, annonsdata |
| A3 | Granskare | Claude | Varumärkesgrind: poäng, Godkänd eller Revidera, skrivregler, faktakontroll mot 00_Underlag | 02_Utkast, 03_Granskning, livv-skrivregler |
| A4 | Contentcreator | Claude | Skriver allt material, organiskt och betalt, enligt brief | 01_Briefer, 00_Underlag, 02_Utkast |
| A5 | Googlespecialist | Claude | SEO, SEM, spårningsplan, sökord, annonstexter, förslag på GTM-ändringar | GA4 Data API, Search Console API, Google Ads API, Tag Manager API |
| A6 | Meta-expert | Claude | Kampanjstruktur, målgrupper, kreativa varianter, optimeringsförslag | Meta Marketing API |
| A7 | LinkedIn-expert | Claude | Organisk plan för företagssidorna, annonsupplägg, B2B-vinklar | LinkedIn Community Management API, Advertising API |
| A8 | X-expert | Grok | Format och ton för X, bevakning av samtal, svarsförslag | xAI API, X API |

Kanalexperterna (A5 till A8) tar fram förslag och utkast. De publicerar aldrig och ändrar aldrig budgetar, bud eller kampanjer.

## Den slutna loopen och statusflödet

Loopen följer statusflödet i livv-grund: Brief, Utkast, Granskning, Godkänt, Publicerad, Arkiverad. Det nya är lärandesteget, där A2:s analys av resultaten blir underlag för A0:s nästa briefer.

Diagram: Varje objekt passerar A3 och Mattias innan det publiceras och mäts.

1. Insikter: A1 trender, A2 lärdomar
2. A0 Director: prioriterar, skriver brief
3. A4 Content: skriver utkast i 02_Utkast
4. A5 till A8: kanalanpassning, kampanjförslag
5. A3 Granskare: varumärkesgrind, poäng minst 4 (Revidera tillbaka till A4, högst 2 varv)
6. Mattias: godkänner varje objekt (människa i loopen)
7. Publicering: människa, från företagssidan (människa i loopen)
8. Mätning: nattlig import till Matregister, lärdomar tillbaka till Insikter

Den slutna loopen · 8 steg, 2 mänskliga grindar

A3 kan skicka tillbaka ett utkast till A4 högst två gånger innan objektet eskaleras. Varje statusbyte följer grundens fyra steg: kontrollera krav, flytta filen, uppdatera raden, logga.

## Rytm och kadens

Teamet arbetar i en veckorytm med daglig bevakning och nattlig datainhämtning. Tiderna är förslag att justera.

| När | Vad | Agent | Utdata |
|---|---|---|---|
| Måndag | Trendspaning på nätet och X, de senaste sju dagarna | A1 | Trendrapport i 13_Insikter |
| Dagligen 06.00, från fas 3 | Bevakning av samtal på X | A8 | Svarsförslag och trender för X |
| Nattligen | Resultatimport från Google, Meta, LinkedIn och X | Skript, ingen agent | Nya rader i Matregister |
| Måndag | Lärdomar, prioritering, veckoplan och briefer | A2, A0 | Briefer i 01_Briefer, rader i registret |
| Tisdag till torsdag | Utkast, kanalanpassning och granskning | A4, A5 till A8, A3 | Utkast i 02_Utkast, granskade objekt i 03_Granskning |
| Fredag | Godkännandepass och veckorapport | Mattias, A0 | Godkända objekt i 04_Godkant, kort rapport |
| Månadsvis | Månadsanalys och underlag till CEO-uppföljningen | A2, A0 | Månadsrapport, uppdaterad statussida |

## Teknisk arkitektur

Ja, teamet kan byggas i Claude Code. Claude Code har de byggstenar som behövs: subagenter med egna instruktioner och verktyg, skills, hooks, MCP-kopplingar och körning utan användare för schemalagda jobb (Claude Code: subagenter).

Diagram: A0 är huvudsessionen och delegerar till åtta subagenter.

- Claude Code-projekt i Git
  - A0 Director: huvudsession, planerar och delegerar
  - Subagenter: A1, A2, A3, A4, A5, A6, A7, A8, var och en med egna verktyg
  - Skills: livv-grund, livv-skrivregler, roller
  - Hooks: spärr mot publicering och radering
- MCP-kopplingar (anropas av subagenterna)
  - SharePoint: Microsoft Graph
  - Google: GA4, GSC, Ads, GTM
  - Meta, LinkedIn, X: läsrätt via API
  - Grok via xAI: trendsök för A1 och A8
- Schemalagd körning: cron eller schemalagd uppgift startar A0

Arkitektur i Claude Code · huvudsession, subagenter, kopplingar

**Huvudsession och subagenter.** Subagenter kan inte starta andra subagenter. Därför körs A0 som huvudsession och delegerar till A1 till A8, som var och en är en Markdown-fil i `.claude/agents/` med egen systemprompt, modell och verktygslista.

**Grok.** Claude Code har ingen inbyggd Grok-koppling. En liten MCP-server mot xAI API ger A1 och A8 ett verktyg för trendsök. Agenten styrs av Claude, men sökningen görs av Grok.

**Var det körs.** Interaktivt arbete sker på Mattias dator, där teamet startas med `./starta.sh` och teamtavlan med `./tavla.sh`. Schemalagda körningar (trendscan, import, veckoplan) behöver en maskin som alltid är igång. Schemalagda uppgifter i skrivbordsappen fungerar bara när datorn är vaken och appen öppen.

Beslut 17 november 2026: de schemalagda körningarna läggs på en liten Linux-server hos IT, som kör Claude Code i headless-läge via cron. Servern behövs först när schemalagda körningar byggs. Underlag till IT:

| Del | Krav |
|---|---|
| Operativsystem | Linux, gärna Ubuntu 24.04 LTS |
| Kapacitet | 2 vCPU, 4 GB RAM (8 GB för parallella körningar), 40 GB disk. Modellen körs hos Anthropic, så servern gör inget tungt arbete. |
| Programvara | Python 3.11 eller senare, Git och Claude Code |
| Nätverk | Utgående HTTPS mot api.anthropic.com, login.microsoftonline.com och graph.microsoft.com. Senare Google, Meta, LinkedIn, X och xAI. Inga inkommande portar utöver IT:s adminåtkomst. |
| Drift | En egen tjänsteanvändare kör jobben. Hemligheterna ligger i en fil som bara den användaren kan läsa, eller i Key Vault. Backup behövs inte för innehållet, som ligger i SharePoint och Git. |
| Säkerhet | Klienthemligheten för appen går ut 16 november 2028. På servern bör den på sikt bytas mot ett certifikat. |

Föreslagen projektstruktur:

```
livv-marketing-team/
  CLAUDE.md                 teamets uppdrag, regler, hänvisning till skills
  .mcp.json                 MCP-servrar: SharePoint, Google, Meta, LinkedIn, X, xAI
  .claude/
    settings.json           behörigheter och hooks
    agents/
      a1-trendspotter.md
      a2-researcher.md
      a3-granskare.md
      a4-contentcreator.md
      a5-google.md
      a6-meta.md
      a7-linkedin.md
      a8-x.md
    skills/
      livv-grund/
      livv-skrivregler/
      (en skill per roll med arbetssätt och mallar)
    hooks/
      sparr-publicering.sh  stoppar publicering, budgetändring, radering
  scripts/
    nattlig-import.py       hämtar resultat till Matregister
```

## Kopplingar och behörigheter

Börja med läsrättigheter överallt. Skrivrätt ges bara till SharePoint-mappen Livv Marketing Ops.

| System | Koppling | Används av | Behörighet från start | Att göra innan |
|---|---|---|---|---|
| SharePoint, Microsoft 365 | Microsoft Graph via MCP-server | Alla | Läs och skriv i Livv Marketing Ops | App-registrering i Entra ID, behörighet avgränsad till webbplatsen |
| GA4 | GA4 Data API, gärna BigQuery-export | A2, A5 | Läs | Tjänstekonto med Viewer-roll |
| Google Search Console | Search Console API | A2, A5 | Läs | Tjänstekonto tillagt som användare |
| Google Ads | Google Ads API | A2, A5 | Läs | Developer token, ansökan och godkännande hos Google |
| Google Tag Manager | Tag Manager API | A5 | Läs | Tjänstekonto med läsrätt |
| Meta | Meta Marketing API | A2, A6 | Läs (ads_read) | Meta-app i Business Manager, systemanvändare, appgranskning |
| Meta Ad Library | Ad Library API | A1, A6 | Läs | Identitetsverifiering hos Meta |
| LinkedIn | Community Management API och Advertising API | A2, A7 | Läs | Ansökan till LinkedIn, kan ta flera veckor, exporter under tiden |
| X | X API | A2, A8 | Läs | Betald API-nivå |
| Grok | xAI API med webb- och X-sökning | A1, A8 | Endast frågor, ingen intern data | API-nyckel, granskning av xAI:s villkor för datalagring |
| Data Core | Databas eller fil via Matregister | A2 | Läs | Mappning av Matregisters kolumner |

Alla nycklar lagras i en hemlighetshanterare eller som miljövariabler på den maskin som kör teamet, aldrig i skills, CLAUDE.md eller dokument.

## Säkerhet och styrning

Reglerna i livv-grund gäller alla nio agenter och hålls tekniskt, inte bara i instruktioner.

- **Behörigheter per agent.** Varje subagent får bara de verktyg rollen kräver. A3 kan läsa och flytta i granskningsflödet men aldrig skapa briefer. A5 till A8 har inga skrivverktyg mot annonsplattformarna.
- **Hooks som spärr.** En hook stoppar varje anrop som skulle publicera, ändra budget, radera filer eller skriva utanför Livv Marketing Ops, oavsett vad agenten fått för instruktion.
- **Människa i loopen.** Inget når 04_Godkant utan Mattias uttryckliga godkännande för just det objektet. Publicering görs av en människa från rätt företagssida.
- **Fakta bara från 00_Underlag.** Trendrapporter från Grok är idéunderlag. En människa för över det som verifierats innan det får användas i material.
- **Inga personuppgifter.** Inga kontaktlistor, leadlistor eller CRM-data till någon modell. Till Grok skickas bara sökfrågor, aldrig internt material.
- **Spårbarhet.** Varje åtgärd loggas i 09_Loggar. Projektet versionshanteras i Git så att ändringar i agenter och skills kan granskas och backas.

## Byggplan i faser

Teamet byggs i fyra faser. Varje fas har en grind som ska vara uppfylld innan nästa startar.

1. **Fas 1: Kärnloopen.** Projektmapp i Git, CLAUDE.md, livv-grund och livv-skrivregler som skills, subagenter för A0, A3 och A4, Microsoft 365-kopplingen och hooks. Resultatdata läggs in manuellt.
   - Grind: tre objekt har gått hela vägen från Brief till Publicerad utan fel i register eller logg.
   - Beslut 17 november 2026: A2 byggs redan i fas 1 och analyserar exporter som Mattias lägger i 11_Dataimport. Kanaler i dag: LinkedIn för Livv.se, Livv.fi och Unique Cosmetics, X för Livv Group, samt GA4, GTM och Search Console för Livv.se, Livv.fi och Unique. Meta är inte registrerat.
2. **Fas 2: Data och Google.** Läskopplingar till GA4, Search Console, Google Ads och GTM, nattlig import till Matregister, subagent för A5. Exporterna till A2 ersätts av automatisk import.
   - Grind: A2 levererar en veckoanalys som Mattias bedömer som användbar. Uppfylld 17 november 2026: analysen 20261117_livv_analys_v43-46_v01.md av Livv.se på LinkedIn bedömdes som mycket bra och användbar. Fyra lärdomar ledde direkt till inlägg för v.48 till 51 och ett test av CTA i stället för fråga.
3. **Fas 3: Sociala kanaler och Grok.** Meta, LinkedIn och X med läsrätt, xAI-kopplingen, subagenter för A1, A6, A7 och A8.
   - Grind: LinkedIns API-ansökan godkänd, eller beslut om att köra vidare på exporter.
4. **Fas 4: Sluten loop på schema.** Schemalagda körningar för trendscan, import och veckoplan, där A2:s lärdomar styr A0:s nästa briefer, plus månadsunderlag till CEO-uppföljningen.
   - Grind: fyra veckor i följd utan manuell handpåläggning i loopen, utom Mattias godkännanden.

Starta LinkedIns och Googles API-ansökningar redan i fas 1, eftersom godkännandet kan ta flera veckor.

## Publicering från tavlan: läge

Beslut 18 november 2026: Mattias kan publicera godkända objekt med knappen Publicera i teamtavlan. Ingen agent publicerar. Se README, "Publicera från tavlan".

**LinkedIn, klart 18 november 2026**
- Appen Livv Marketing Ops är skapad och verifierad mot företagssidan Livv.se (organisations-id 42934065).
- Kvadratisk logotyp uppladdad. Redirect URL `http://localhost:8787/linkedin/svar`.
- Länk till integritetspolicy i appen: livv.se/se/integritetspolicy.
- Branschen på Livv.se är ändrad från Wholesale till Hospitality.
- Mattias har lagt in appens nycklar och sidan i sin lokala konfiguration.

**LinkedIn, blockerat**
- Integritetspolicyn på livv.se/se/integritetspolicy är tom. Livv.fi har en på finska för Guest Comfort Oy, som inte passar. Webbansvarig tar fram texten och den som ansvarar för GDPR godkänner den. Den skrivs inte av en agent.

**LinkedIn, kvar**
1. När policyn ligger ute: kontrollera sidan och begär Community Management API i appen. Inga andra produkter i samma app.
2. LinkedIns granskning, ofta flera veckor.
3. När den är godkänd: logga in med LinkedIn i tavlan. Inloggningen gäller i 60 dagar.
4. Livv.fi läggs till som sida när den ska användas.

**X, kvar**
- Mattias lägger in nycklarna för Livv Groups utvecklarapp, med behörigheten Read and write och Access Token skapad för Livv Groups konto.

**Bildbrief till Brand Studio, 23 november 2026**
- Mattias har byggt flödet Livv bildbrief till Brand Studio i Power Automate. Det reagerar när en fil med image-brief i namnet skapas i Livv Marketing Ops/12_Pictures och skickar en ping i Teams via Flow bot.
- Testpingen kom fram. Anastasia har redigeringsrätt i 12_Pictures, och pingen går nu till henne.
- Kopplingarna går via Mattias Microsoft-konto. Jesper på IT har fått frågan om att flytta dem till ett tjänstekonto.

**A1 Trendspotter, 23 november 2026**
- Beslut: A1 byggs nu, före grinden till fas 3, medan teamet väntar på LinkedIns ansökan. Grok är godkänt internt.
- Byggt: MCP-servern mot xAI med verktyget trendsok, verktyget spara_trendrapport för 13_Insikter, subagenten a1-trendspotter och spärrar så att bara A1 söker och sparar trendrapporter.
- Beslut 23 november 2026: A1 söker en gång i veckan, på måndagar, inte varje morgon. A0 startar spaningen första gången teamet arbetar en vecka, samtidigt som A2:s veckoanalys. Därutöver när Mattias ber om det. Körning på schema utan att teamet är startat kommer i fas 4.
- Första riktiga körningen 23 november 2026: trender inom spa och wellness, 9 till 23 november. Rapporten 13_Insikter/20261123_trender_spa_v01.md sparades och loggades. Modellen grok-4-1-fast och svarsformatet fungerade.

**Arbetsregler för kopplingarna**
- Agenter godkänner aldrig avtal eller villkor och skickar inga meddelanden för Mattias räkning.
- Hemliga nycklar läggs in av Mattias själv, aldrig av en agent.

## Öppna frågor och beslut

Beslutat: A3 behålls som egen granskare, teamet består av nio roller.

Beslutat: spärren tillåter `git ls-remote` och `git fetch` i drift och `gh` i utvecklingsläge. Radering via `gh` är alltid spärrad.

Beslutat 24 november 2026:
- Bilder som publiceras har aldrig text. Gäller även citatkort, FAQ-kort och kampanjgrafik. Står i livv-skrivregler.
- Positioneringen är alltid "hospitality partner", för Livv Group, Livv.se och Livv.fi. Aldrig "authority". Står i livv-skrivregler.
- Unique har certifieringar. Vilka standarder och certifikat det gäller ska läggas i 00_Underlag innan de nämns i material.
- En innehållsplan för januari till mars 2027 tas fram för Livv Group, Livv och Unique.

Beslutat 23 november 2026: Claude i Chrome får ändra i Excel-filerna i SharePoint på Mattias uppdrag, enligt avsnittet Skriva i Excel-filerna i livv-grund. Publicering ingår inte.

- [ ] Stämmer föreslagen numrering A0 till A8 med hur A1, A2 och A4 till A7 redan är definierade i livv-grund?
- [x] Var körs teamet: på en dator som alltid är igång, en server eller i molnet? Beslut 17 november 2026: på Mattias dator, och schemalagda körningar på en liten Linux-server hos IT. Se Var det körs.
- [ ] Vilken mapp blir insiktsmapp för trendrapporter, och vem verifierar innehållet innan det når 00_Underlag? Beslut 23 november 2026: en ny huvudmapp, 13_Insikter, i Livv Marketing Ops. Mattias skapar den. Mattias verifierar innehållet.
- [ ] Vem ansöker om API-åtkomst hos Google Ads, Meta och LinkedIn, och när?
- [ ] Vilken API-nivå hos X behövs, eller räcker Groks inbyggda X-sökning?
- [x] Godkänner IT och dataskydd att sökfrågor skickas till xAI, efter granskning av villkoren? Beslut 23 november 2026: Grok är godkänt internt, enligt Mattias. Till Grok skickas fortfarande bara sökfrågor, aldrig internt material.
- [ ] Hur ser Data Core ut tekniskt, och hur läser A2 från den?
- [ ] Vem är ersättare för godkännanden när Mattias är borta?
