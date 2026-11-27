---
title: "Claude privātuma audits — lietošanas instrukcija"
subtitle: "Versija 2.0 · macOS, Windows, Linux · Claude Desktop, Cowork, Claude Code, VS Code/Cursor, GitHub repozitoriji"
---

# 1. Kam tas paredzēts

Skripts `claude_privatuma_audits.py` regulāri pārbauda visu, ko Claude lasa un izpilda tavās ierīcēs, un meklē komandas vai tekstus, kas var apdraudēt privātumu:

- datu nosūtīšana uz ārējiem serveriem (curl POST, webhook pakalpojumi, nc, scp);
- piekļuve parolēm, atslēgām, Keychain, pārlūku datiem, e-pastam un ziņām;
- slēptas instrukcijas Claude (piem. "ignorē iepriekšējās instrukcijas", "neko neasti lietotājam", neredzami Unicode simboli);
- aizmiglots vai attālināti lejupielādēts kods (`curl | bash`, base64, PowerShell `-enc`);
- pastāvīga ievietošanās sistēmā (launchd, cron, schtasks, `.zshrc`);
- ekrāna, mikrofona un starpliktuves pārtveršana;
- bīstami iestatījumi: `bypassPermissions`, `Bash(*)`, hooks, trafika novirzīšana caur svešu serveri;
- MCP serveri: attālie URL ārpus uzticamo saraksta, `http://`, `npx` bez fiksētas versijas, `sh -c`.

Skripts **tikai lasa** failus un neko neizpilda, nemaina un nesūta uz internetu. Rezultāti paliek tavā datorā mapē `~/.claude-audit/`.

# 2. Kur Claude tiek lietots un kā tas tiek pārklāts

| Platforma | Kas tiek pārbaudīts | Kā |
|---|---|---|
| **Claude Desktop un Cowork** (Mac/Windows) | `claude_desktop_config.json`, `local-agent-mode-sessions` (sinhronizētie skill un plugin), Extensions | automātiski |
| **Claude Code CLI** | `~/.claude/` (skills, commands, agents, hooks, plugins, settings, CLAUDE.md), `~/.claude.json` (MCP), pārvaldītie iestatījumi | automātiski |
| **VS Code, Cursor, Windsurf** | `mcp.json`, `settings.json`, `~/.cursor/`, `.windsurfrules` | automātiski |
| **Claude Code tīmeklī (mākonī)** | repozitoriju `.claude/`, `CLAUDE.md`, `.mcp.json` (šos failus mākoņa sesija lasa un hooks tur izpilda) | automātiski lokāli klonētiem repo; citiem ar `--git URL` |
| **Eksportēti skill** (`.skill`, `.zip`, `.plugin`) | visi teksta faili arhīvā | `--path fails.skill` |
| **claude.ai tīmekļa vietne, iPhone, iPad** | Connectors, skill, atmiņa, kopīgotās saites | **manuāli**, ik mēnesi ar `--checklist` |

Mobilajās lietotnēs lokālu failu nav, bet tās izmanto to pašu kontu un savienojumus kā tīmekļa vietne. Tāpēc tās pārklāj manuālā pārbaude (sadaļa 7).

# 3. Uzstādīšana

Vajadzīgs tikai Python 3.8 vai jaunāks, bez papildu pakotnēm. Pārbaude: `python3 --version` (Windows: `py --version`).

## 3.1. macOS
1. Lejupielādē `claude_privatuma_audits.py` no GitHub (repozitorijs `SAAB`, atzars `claude/elegant-feynman-il9yba`) un saglabā, piem., mapē `~/Downloads`.
2. Terminālī:
   ```bash
   cd ~/Downloads
   python3 claude_privatuma_audits.py            # pirmā pārbaude
   python3 claude_privatuma_audits.py --install-schedule --time 09:07
   python3 ~/.claude-audit/claude_privatuma_audits.py --status
   ```
3. Pirmajā reizē macOS var jautāt par paziņojumu atļauju: System Settings → Notifications → Script Editor vai Terminal → Allow.

## 3.2. Windows
1. Saglabā failu, piem., `C:\Users\<tu>\Downloads\`.
2. PowerShell:
   ```powershell
   cd $HOME\Downloads
   py claude_privatuma_audits.py
   py claude_privatuma_audits.py --install-schedule --time 09:07
   py $HOME\.claude-audit\claude_privatuma_audits.py --status
   ```
3. Grafiks tiek izveidots kā Task Scheduler uzdevums `ClaudePrivatumaAudits`. Ja dators ir izslēgts plkst. 09:07, uzdevums tajā dienā nepalaižas. Par to brīdina `--status` un nākamā palaišana (sk. 6. sadaļu).

## 3.3. Linux
Tas pats, ko macOS. Grafiks tiek ierakstīts `crontab` ar komentāru `# claude-privatuma-audits`. Paziņojumam tiek izmantots `notify-send`, ja tas ir pieejams.

## 3.4. Katra ierīce atsevišķi
Skripts jāuzstāda **katrā datorā**, kur lieto Claude (Mac, Windows, Linux). Katrai ierīcei ir sava bāzlīnija un vēsture `~/.claude-audit/`.

## 3.5. Pirmā konfigurēšana
Pēc pirmās palaišanas atver `~/.claude-audit/config.json` (Windows: `C:\Users\<tu>\.claude-audit\config.json`):

| Lauks | Nozīme |
|---|---|
| `allowed_domains` | uzticamie domēni; citi tiek atzīmēti kā NET-01. Jau ir Microsoft, Google, GitHub, Anthropic, `lsb.lv`, `likumi.lv`, `vm.gov.lv`, `nvd.gov.lv` u.c. |
| `personal_terms` | tavi personas dati (e-pasts, tālrunis), piem. `["tavs@epasts.lv"]`. Ja tie parādās failā līdzās nezināmam ārējam domēnam, tiek ziņots kā HIGH (PRIV-01). |
| `repo_roots` | mapes, kurās meklēt git repozitorijus (papildus `~/GitHub`, `~/Developer`, `~/Documents/GitHub`, `~/code`, `~/src` u.c.) |
| `ignore_paths` / `ignore_rules` | ko neskenēt (piem. `["/node_modules/"]`, `["OBF-02"]`) |
| `stale_hours` | pēc cik stundām bez pārbaudes `--status` ziņo par kļūmi (36) |
| `checklist_days` | cik bieži atkārtot manuālo pārbaudi (30) |

# 4. Ikdienas lietošana

| Komanda | Ko dara |
|---|---|
| `python3 claude_privatuma_audits.py` | pilna pārbaude, izvade terminālī, pārskats saglabājas |
| `--min-severity HIGH` | rāda tikai nopietnos atradumus |
| `--path ~/Downloads/jauns.skill` | pārbauda jaunu skill **pirms** instalēšanas |
| `--repos ~/Dev` | papildu mape ar git repozitorijiem |
| `--git https://github.com/org/repo` | pārbauda attālu repozitoriju (shallow clone, kods netiek izpildīts) |
| `--json` | mašīnlasāma izvade |
| `--show-accepted` | rāda arī apstiprinātos atradumus |

**Noteikums:** pirms katra jauna skill, plugin vai MCP servera uzstādīšanas palaid `--path` pārbaudi.

# 5. Kā lasīt rezultātus

## 5.1. Smaguma līmeņi

| Līmenis | Nozīme | Rīcība |
|---|---|---|
| **CRITICAL** | attālā koda izpilde, Keychain piekļuve | nekavējoties: atslēdz/dzēs avotu, sk. 5.3 |
| **HIGH** | datu nosūtīšana, akreditācijas dati, slēptas instrukcijas, apiešanas karodziņi | izmeklē vienas dienas laikā |
| **MEDIUM** | hooks, plašas atļaujas, nepiesprausti MCP, nezināmi domēni kopā ar tīkla kodu | pārskati nedēļas laikā |
| **LOW** | informatīvi (uzticami attālie MCP, nodotās atslēgas) | zināšanai |

Katram atradumam ir **ID** (`#4fa608…`), noteikuma kods (piem. `EXFIL-01`), faila ceļš ar rindas numuru un fragments. Slepenas atslēgas fragmentos tiek paslēptas.

## 5.2. Bieži viltus trauksmes gadījumi
- Skill, kas **apraksta** drošību vai satur piemērus (piem. "nekad nesūti datus uz ārieni"), var izraisīt atradumu. Atver failu un izlasi kontekstu.
- `NET-01` nozīmē tikai to, ka domēns nav tavā atļauto sarakstā. Ja domēns ir tavs vai uzticams, pievieno to `allowed_domains`.
- Hooks (`HOOK-01`) ir MEDIUM vienmēr, jo tie izpildās automātiski. Izlasi komandu un, ja tā ir tava, apstiprini.

## 5.3. Ko darīt ar patiesu atradumu
1. **Neizpildi un neatver** aizdomīgo failu citur. Pārtrauc Claude sesiju, kas to izmanto.
2. Izņem skill, plugin vai MCP serveri (dzēs failu vai atvieno claude.ai → Settings).
3. Ja atradums bija par datu nosūtīšanu vai akreditācijas datiem: nomaini paroles un API atslēgas, ko skripts varēja redzēt (GitHub tokeni, brokeru piekļuve, Microsoft/Google paroles), un pārbaudi trešo pušu piekļuves (sadaļa 7).
4. Pārbaudi `~/.claude-audit/reports/`, lai redzētu, kad atradums parādījās pirmo reizi (`🆕`).
5. Pēc risinājuma palaid pārbaudi vēlreiz, atradumam jāpazūd.

## 5.4. Atradumu apstiprināšana
Pēc tam, kad esi pats pārbaudījis, ka atradums ir drošs:
```bash
python3 claude_privatuma_audits.py --accept 4fa608fd248d4aca     # viens vai vairāki ID
python3 claude_privatuma_audits.py --accept ALL                  # visi pašreizējie (tikai pēc pilnas pārlasīšanas!)
python3 claude_privatuma_audits.py --unaccept 4fa608fd248d4aca   # atcelt
```
Apstiprinātie atradumi netiek skaitīti, nerada paziņojumus un neietekmē atgriezes kodu. **Ja faila saturs mainās, atradums parādās atkal**, jo ID ir saistīts ar saturu. Vienu rindu var arī atzīmēt ar komentāru `audit-ignore` pašā failā.

## 5.5. Atļauju labošana: kods tiek palaists tikai ar tavu apstiprinājumu

Claude Code atļaujām ir trīs saraksti: `allow` (palaiž bez jautāšanas), `ask` (vienmēr jautā) un `deny` (aizliegts). Rindas, piemēram, `Bash(python3 *)`, `mcp__…__place_order` vai `Read(~/.ssh/…)` sarakstā `allow` nozīmē, ka Claude (vai slēpta instrukcija kādā failā vai tīmekļa lapā) var tās izmantot bez tava ziņa.

```bash
python3 claude_privatuma_audits.py --fix-permissions            # jautā par katru failu (j/N)
python3 claude_privatuma_audits.py --fix-permissions --yes      # visus uzreiz
python3 claude_privatuma_audits.py --fix-permissions --path ~/projekts   # konkrēta mape
```

- Riskantās atļaujas tiek **pārvietotas uz `ask`**, nevis dzēstas. Claude turpmāk katru reizi jautās, un kods tiek palaists tikai tad, kad tu to apstiprini.
- Pirms izmaiņām tiek izveidota rezerves kopija `settings.local.json.bak-GGGGMMDD-HHMMSS`. Atcelt var, atjaunojot to.
- Drošās atļaujas (piem., `Bash(git status)`, `get_price_snapshot`) un `deny` saraksts netiek aiztikti.
- **Ieteikums:** kad Claude jautā par komandu, izvēlies **Yes (vienreiz)**, nevis "Yes, and don't ask again". Otrā izvēle ir tā, kas ieraksta plašās atļaujas `allow` sarakstā.
- Ja kādu komandu tiešām vajag atļaut pastāvīgi, ieraksti to **šauri**: `Bash(python3 scripts/mans_skripts.py:*)`, nevis `Bash(python3 *)`.

# 6. Kontrole — kā pārliecināties, ka audits tiešām darbojas

## 6.1. `--status`
```bash
python3 ~/.claude-audit/claude_privatuma_audits.py --status
```
Rāda un pārbauda:

- `[OK]/[!!] Ikdienas grafiks` — vai launchd/schtasks/cron uzdevums ir aktīvs;
- `Skripta integritāte` — vai uzstādītais skripts nav mainīts kopš instalēšanas (kontrolsummas salīdzinājums);
- `Pēdējā pārbaude` — cik sen pārbaude notikusi; ja vecāka par `stale_hours`, tas ir sarkans signāls;
- `Manuālā pārbaude` — vai šomēnes veikts `--checklist`;
- aktīvo atradumu skaits.

Atgriezes kods `3` nozīmē, ka kaut kas jālabo.

## 6.2. Vēsture un pārskati
- `--history` parāda pēdējās 15 palaišanas: laiks, ierīce, failu skaits, atradumi pa līmeņiem, jaunie atradumi, skripta kontrolsummas sākums.
- Pilni pārskati: `~/.claude-audit/reports/GGGG-MM-DD_HHMM.md` (glabājas pēdējie 60) un `pedejais.json`.
- Vēsture: `~/.claude-audit/runs.jsonl`.

## 6.3. Automātiskie brīdinājumi
Paziņojums (macOS, Windows, Linux) un ieraksts `~/.claude-audit/BRIDINAJUMS.txt` rodas, ja:

- parādās **jauns** HIGH vai CRITICAL atradums (nav katru dienu vienas un tās pašas lietas);
- tiek mainīts paša audita skripts (iespējama sabotāža);
- iepriekšējā pārbaude bija pārāk sen (grafiks nedarbojās) vai manuālā pārbaude nav veikta (parādās pārskata sākumā).

## 6.4. Skripta aizsardzība
- Uzstādītais skripts atrodas `~/.claude-audit/`. Neļauj Claude to rediģēt (nelūdz Claude "uzlabot" šo failu, strādā tikai ar savu kopiju repozitorijā).
- Atjauninot skriptu: palaid `--install-schedule` no jaunās versijas, tas pārraksta kontrolsummu.
- Ja `--status` ziņo "SKRIPTS IR MAINĪTS", tev nav jāuzticas tā rezultātiem. Pārinstalē no GitHub un pārbaudi, kas mainījis failu (PERS-03 noteikums arī meklē skill, kas raksta uz `.claude/`).

## 6.5. Ieteicamais kontroles ritms

| Cik bieži | Ko |
|---|---|
| Katru dienu (automātiski) | pārbaude plkst. 09:07 |
| Katru reizi, kad parādās paziņojums | izmeklē atradumu (5.3) |
| Pirms katra jauna skill/plugin/MCP | `--path` pārbaude |
| Reizi nedēļā (2 min) | `--status` katrā ierīcē |
| Reizi mēnesī | `--checklist` (web, telefons, Connectors) un `--checklist-done` |
| Pēc ierīces nomaiņas vai atjaunošanas | atkārtota uzstādīšana (3. sadaļa) |

# 7. Manuālā pārbaude (to, ko skripts nevar redzēt)

Komanda `python3 claude_privatuma_audits.py --checklist` izdrukā kontrolsarakstu. Kopsavilkums:

1. **claude.ai → Settings → Connectors:** atvieno nelietotos (Microsoft 365, Gmail, GitHub, Slack u.c.), pārbaudi tiesības (lasīšana vs. sūtīšana/dzēšana), dzēs nepazīstamus custom connectors.
2. **claude.ai → Settings → Capabilities / Skills:** pārbaudi katru skill (lejupielādē un palaid `--path`), izlasi Projects instrukcijas un atmiņu.
3. **Trešo pušu konti:** Microsoft (`account.microsoft.com`, `myapps.microsoft.com`), Google (`myaccount.google.com/permissions`), GitHub (`github.com/settings/installations` un `/settings/applications`), tiesības tikai vajadzīgajiem repozitorijiem.
4. **Claude Code tīmekļa vide:** Environments (tīkla režīms, atļautie hosti, vides mainīgie bez noslēpumiem, setup skripts) un repozitoriju hooks (`--git URL`).
5. **iPhone/iPad:** lokāli nav ko skenēt. Pārbaudi tikai kopīgotās saites un artefaktus.
6. **Citi datori:** `--status` katrā.

Kad pabeigts: `python3 claude_privatuma_audits.py --checklist-done`. Ja to nedara ilgāk par 30 dienām, `--status` un pārskats atgādina.

# 8. Atinstalēšana

```bash
python3 ~/.claude-audit/claude_privatuma_audits.py --uninstall-schedule
rm -rf ~/.claude-audit              # Windows: Remove-Item -Recurse $HOME\.claude-audit
```

# 9. Ierobežojumi un godīga piezīme

- Skripts ir **noteikumu (regulāro izteiksmju) pārbaudītājs**. Tas atrod zināmus bīstamus paraugus, bet nevar garantēt, ka nav nekā ļauna. Dīvaini formulēts vai tikai dabiskā valodā rakstīts uzbrukums var palikt nepamanīts.
- Netiek skenēti Claude sarunu vēstures faili (`.jsonl`), binārie faili un nesinhronizēti tīmekļa skill.
- Aizsardzība balstās arī uz ieradumiem: instalē skill tikai no uzticamiem avotiem, atvieno nelietotos Connectors, nelieto `bypassPermissions` un nelaid Claude rediģēt audita skriptu.
- Skripts nesūta nekādus datus uz internetu. Vienīgā tīkla darbība ir tava izvēlētā `--git` klonēšana.

# 10. Ātrā atsauce

```text
Pārbaude:         python3 claude_privatuma_audits.py [--min-severity HIGH] [--path X] [--repos DIR] [--git URL]
Grafiks:          --install-schedule [--time HH:MM]    --uninstall-schedule
Kontrole:         --status    --history
Atradumi:         --accept ID|ALL    --unaccept ID    --show-accepted    --detail
Atļaujas:         --fix-permissions [--yes] [--path X]
Manuāli:          --checklist    --checklist-done
Atgriezes kods:   0 tīrs/LOW · 1 MEDIUM · 2 HIGH/CRITICAL · 3 kontroles problēma (--status)
Dati:             ~/.claude-audit/ (config.json, reports/, runs.jsonl, BRIDINAJUMS.txt)
```
