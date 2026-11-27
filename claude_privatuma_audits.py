#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude privātuma audits v2 (macOS · Windows · Linux)
====================================================
Pārbauda visu, ko Claude lasa un izpilda šajā datorā: skill, aģentus, komandas,
instrukcijas (CLAUDE.md / AGENTS.md), hooks, atļaujas, MCP savienojumus,
Claude Desktop / Cowork / Claude Code CLI / VS Code / Cursor konfigurāciju un
git repozitorijus (kurus lasa arī Claude Code tīmekļa sesijas). Meklē komandas
un tekstus, kas var apdraudēt privātumu.

Pārbaude:
    python3 claude_privatuma_audits.py                  # pilna pārbaude
    python3 claude_privatuma_audits.py --path X         # papildu fails/mape/.skill/.zip
    python3 claude_privatuma_audits.py --repos ~/Dev    # papildu mape ar git repozitorijiem
    python3 claude_privatuma_audits.py --git URL        # pārbauda attālu repozitoriju (shallow clone)
    python3 claude_privatuma_audits.py --min-severity MEDIUM --json

Kontrole un uzraudzība:
    --install-schedule [--time 09:07]   ikdienas automātiska palaišana (launchd / schtasks / cron)
    --uninstall-schedule
    --status                            vai grafiks darbojas, vai skripts nav mainīts, cik sen pārbaudīts
    --history                           pēdējo palaišanu vēsture
    --accept ID|ALL / --unaccept ID     atzīt pārbaudītu atradumu par drošu
    --fix-all [--yes]                   viss vienā reizē (atļaujas + Desktop Commander)
    --fix-permissions [--yes]           riskantās atļaujas no 'allow' uz 'ask' (Claude vienmēr jautās)
    --checklist / --checklist-done      manuālā pārbaude tam, ko nevar redzēt lokāli (web, telefons, Connectors)

Atgriezes kods: 0 = tīrs/LOW, 1 = ir MEDIUM, 2 = ir HIGH/CRITICAL, 3 = problēma ar kontroli (--status).
Konfigurācija: ~/.claude-audit/config.json. Rindu var atzīmēt kā drošu ar komentāru: audit-ignore
Pilna instrukcija: INSTRUKCIJA_Claude_privatuma_audits.md
"""
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def host_of(u):
    """Droša hostname izvilkšana; kļūdains URL (piem. http://[x) neapstādina skenēšanu."""
    try:
        return urlparse(str(u)).hostname
    except ValueError:
        return None

HOME = Path.home()
SYS = platform.system()          # Darwin | Windows | Linux
VERSION = "2.1"
WORK = HOME / ".claude-audit"
CONFIG = WORK / "config.json"
STATE = WORK / "state.json"
REPORTS = WORK / "reports"
RUNS = WORK / "runs.jsonl"
ACCEPTED = WORK / "accepted.json"
CHECKLIST = WORK / "checklist.json"
SCRIPT_HASH = WORK / "script.sha256"
ALERT = WORK / "BRIDINAJUMS.txt"
LABEL = "lv.lsb.claude-privatuma-audits"
PLIST = HOME / "Library/LaunchAgents" / f"{LABEL}.plist"
WIN_TASK = "ClaudePrivatumaAudits"
CRON_MARK = "# claude-privatuma-audits"

SEV_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
COLORS = {"CRITICAL": "\033[1;95m", "HIGH": "\033[1;91m", "MEDIUM": "\033[93m",
          "LOW": "\033[96m"}
RESET = "\033[0m"

DEFAULT_CONFIG = {
    "allowed_domains": [
        "anthropic.com", "claude.ai", "claude.com", "github.com",
        "githubusercontent.com", "npmjs.com", "npmjs.org", "pypi.org",
        "python.org", "modelcontextprotocol.io", "microsoft.com",
        "office.com", "microsoftonline.com", "google.com", "googleapis.com",
        "apple.com", "w3.org", "openxmlformats.org", "example.com",
        "localhost", "127.0.0.1", "interactivebrokers.com", "ibkr.com", "likumi.lv", "mk.gov.lv", "vm.gov.lv",
        "nvd.gov.lv", "spkc.gov.lv", "lsb.lv", "saeima.lv", "wikipedia.org",
    ],
    "personal_terms": [],          # piem. e-pasts, tālrunis, personas kods
    "ignore_rules": [],            # piem. ["OBF-02"]
    "ignore_paths": [],            # apakšvirknes, piem. ["/node_modules/"]
    "extra_paths": [],             # papildu mapes/faili, ko skenēt vienmēr
    "repo_roots": [],              # mapes, kurās meklēt git repozitorijus
    "stale_hours": 36,             # cik ilgi bez pārbaudes uzskatīt par kļūmi
    "checklist_days": 30,          # cik bieži atkārtot manuālo pārbaudi
}

# ---------------------------------------------------------------- noteikumi
# (id, smagums, nosaukums, regex)
RULES = [
    ("EXFIL-01", "HIGH", "Datu nosūtīšana ar curl/wget",
     r"\b(curl|wget)\b[^\n]*(\s-d\b|--data|--data-binary|--data-raw|\s-F\b|--form|\s-T\b|--upload-file|-X\s*(POST|PUT)|--post-)"),
    ("EXFIL-02", "HIGH", "Zināms datu savākšanas/webhook pakalpojums",
     r"(discord(app)?\.com/api/webhooks|hooks\.slack\.com|webhook\.site|requestbin|pipedream\.net|ngrok(-free)?\.(io|app|dev)|transfer\.sh|pastebin\.com|paste\.ee|0x0\.st|file\.io|interact\.sh|oast\.(pro|live|site|online|fun|me)|trycloudflare\.com|api\.telegram\.org/bot|burpcollaborator)"),
    ("EXFIL-03", "HIGH", "Tiešs tīkla savienojums (nc/ncat/dev/tcp)",
     r"(\b(nc|ncat|netcat)\s+(?!-\w*z)(-\w+\s+)*(?!127\.0\.0\.1|localhost)[\w.-]+\s+\d{2,5}\b|/dev/(tcp|udp)/)"),
    ("EXFIL-04", "MEDIUM", "Failu pārsūtīšana uz attālu serveri (scp/rsync/sftp)",
     r"\b(scp|rsync|sftp)\b[^\n]*\s[\w.-]+@[\w.-]+:"),
    ("EXFIL-05", "LOW", "HTTP POST/PUT no koda",
     r"(requests\.(post|put)\(|httpx\.(post|put)\(|method\s*[:=]\s*['\"](POST|PUT)['\"]|navigator\.sendBeacon)"),
    ("CRED-01", "HIGH", "Piekļuve atslēgām/akreditācijas datiem (.ssh, .aws, .kube, .netrc…)",
     r"(\.ssh/(id_|config|known_hosts|authorized_keys)|\.aws/(credentials|config)|\.gnupg\b|\.kube/config|\.netrc\b|\.docker/config\.json|\.npmrc\b|\.pypirc\b|\.git-credentials|\.config/gh/hosts)"),
    ("CRED-02", "CRITICAL", "Piekļuve macOS Keychain",
     r"(\bsecurity\s+(find|dump|export|add)-?(generic|internet|keychain|identity)?[- ]?(password|keychain)?\b[^\n]*(-w|-s|dump)|Library/Keychains|login\.keychain|security\s+dump-keychain)"),
    ("CRED-03", "HIGH", "Pārlūka dati (paroles, sīkdatnes, vēsture)",
     r"(Chrome/[^\s\"']*(Login Data|Cookies|Web Data|History)|Firefox/Profiles|cookies\.sqlite|logins\.json|Safari/(Cookies|History|LastSession)|Library/Cookies|Brave-Browser|Microsoft Edge/Default)"),
    ("CRED-04", "HIGH", "Personiskie dati: Messages/Mail/Kontakti/Piezīmes/TCC",
     r"(Library/Messages|chat\.db\b|Library/Mail\b|AddressBook|NoteStore\.sqlite|com\.apple\.TCC|TCC\.db|Library/Calendars)"),
    ("CRED-05", "LOW", "Vides mainīgo (slepeno atslēgu) izvilkšana",
     r"(\bprintenv\b|\benv\s*\|\s*(curl|nc|base64|openssl)|JSON\.stringify\(process\.env\)|os\.environ(\.copy\(\)|\.items\(\))[^\n]*(requests|urlopen|post|curl))"),
    ("CRED-06", "LOW", ".env faila lasīšana",
     r"\b(cat|less|more|head|tail|source|open|read)\b[^\n]*\s[\w./~-]*\.env\b"),
    ("SECRET-01", "HIGH", "Failā cieti ierakstīta slepenā atslēga/token",
     r"(sk-ant-[\w-]{20,}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{30,}|github_pat_[\w]{30,}|xox[abprs]-[\w-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)"),
    ("INJ-01", "HIGH", "Instrukciju ignorēšana (prompt injection)",
     r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)*(previous|prior|above|earlier|system|safety)\s+(instructions|rules|prompts?|guidelines|messages)"),
    ("INJ-02", "HIGH", "Prasība slēpt darbības no lietotāja",
     r"((do not|don'?t|never|must not)\s+(tell|inform|mention|reveal|show|notify|disclose|alert)\s+(this|it|that|these|those|any of (this|these))\b[^\n]{0,30}\b(user|human|person)|without\s+(telling|informing|notifying|alerting)\s+the\s+(user|human)|hide\s+(this|it)\s+from|keep\s+(this|it)\s+(secret|hidden|confidential)\s+from|nesaki\s+lietotājam|neinformē\s+lietotāj)"),
    ("INJ-03", "MEDIUM", "Slepenas/fona darbības formulējums",
     r"(\b(silently|secretly|covertly|stealthily)\s+(send|upload|post|forward|exfiltrate|transmit|copy|collect|install|run|execute|download)\b|\b(send|upload|post|forward|transmit|copy|collect)\b[^\n]{0,40}\b(silently|secretly|covertly)\b)"),
    ("INJ-04", "HIGH", "Prasība sūtīt sarunu/atmiņu/personas datus uz ārieni",
     r"(send|upload|post|forward|exfiltrate|transmit|leak)[^\n]{0,60}(conversation|chat history|memory|memories|user'?s? (data|files|email|name|contacts|documents)|system prompt|credentials|api[ _-]?keys?|passwords?)[^\n]{0,80}(to\s+https?://|to\s+(the\s+)?(server|endpoint|url|webhook|address)|via\s+(http|email))"),
    ("INJ-05", "HIGH", "Drošības/atļauju apiešanas karodziņi",
     r"(--dangerously-skip-permissions|dangerouslyDisableSandbox|--no-verify-ssl|NODE_TLS_REJECT_UNAUTHORIZED\s*[=:]\s*['\"]?0|curl\s[^\n]*\s(-k|--insecure)\b)"),
    ("INJ-06", "MEDIUM", "Aicinājums izslēgt apstiprinājumus/drošību",
     r"(auto-?(approve|accept)\b|always\s+(approve|allow)\s+(all|every)|skip\s+(the\s+)?(permission|confirmation|approval)\s+(prompt|check|step)s?|never\s+ask\s+(the\s+user\s+)?(for\s+)?(confirmation|permission)|disable\s+(the\s+)?(sandbox|permission\s+(prompt|check)s?|safety))"),
    ("OBF-01", "CRITICAL", "Attālā koda lejupielāde un izpilde / base64 izpilde",
     r"((curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b|base64\s+(-d|-D|--decode)[^\n]*\|\s*(sudo\s+)?(ba|z)?sh\b|eval\s*\(?\s*\"?\$\(\s*(curl|wget)|python3?\s+-c\s+[^\n]*\b(exec\s*\(|b64decode|urlopen)|(bash|sh)\s+<\(\s*(curl|wget))"),
    ("OBF-02", "LOW", "Dinamiska koda izpilde / dekodēšana (eval, atob…)",
     r"(\beval\s*[\(\$\"']|\bnew Function\(|base64\.b64decode|\batob\(|(\\x[0-9a-fA-F]{2}){8,})"),
    ("PERS-01", "HIGH", "Pastāvīga ievietošanās (launchd/cron/login items)",
     r"(launchctl\s+(load|bootstrap|submit|enable)|Library/LaunchAgents|Library/LaunchDaemons|\bcrontab\s+(-e\b|-r\b|-\s|[\w./~-]+\.(cron|txt|tab)\b)|/etc/cron|osascript[^\n]*login item|sfltool|systemctl\s+enable)"),
    ("PERS-02", "HIGH", "Shell profila (.zshrc/.bashrc…) modificēšana",
     r"((?<=\S)\s*>{1,2}\s*[\"']?~?/?[\w./$-]*\.(zshrc|zshenv|zprofile|bashrc|bash_profile|profile)\b|\btee\s+-a\s+[^\n]*\.(zshrc|zshenv|zprofile|bashrc|bash_profile)|sed\s+-i[^\n]*\.(zshrc|zshenv|zprofile|bashrc|bash_profile))"),
    ("PERS-03", "MEDIUM", "Claude iestatījumu/instrukciju modificēšana no skripta",
     r"((?<=\S)\s*>{1,2}\s*[\"']?[^\s\"']*\.claude/(settings|CLAUDE|hooks|skills|agents)|\b(tee(\s+-a)?|sed\s+-i|mv|cp)\s+[^\n]*\.claude/(settings|CLAUDE|hooks|skills|agents)|(?<=\S)\s*>{1,2}\s*[\"']?[^\s\"']*\.claude\.json)"),
    ("WIN-01", "CRITICAL", "PowerShell: attālā koda izpilde / kodēta komanda",
     r"((iwr|irm|Invoke-WebRequest|Invoke-RestMethod|DownloadString|DownloadFile)[^\n]*\|\s*(iex|Invoke-Expression)|powershell[^\n]*\s-(enc|encodedcommand|e)\s+[A-Za-z0-9+/=]{20,}|certutil[^\n]*-urlcache|bitsadmin[^\n]*/transfer)"),
    ("WIN-02", "HIGH", "Windows: pastāvīga ievietošanās (schtasks/Run atslēga/Startup)",
     r"(schtasks(\.exe)?\s+/create|reg(\.exe)?\s+add[^\n]*CurrentVersion[\\/]Run|CurrentVersion[\\/]Run\b|Start Menu[\\/]Programs[\\/]Startup|New-ScheduledTask|Register-ScheduledTask)"),
    ("WIN-03", "HIGH", "Windows: akreditācijas dati / pārlūka dati / LSASS",
     r"(\bcmdkey\b|\bvaultcmd\b|Credential Manager|mimikatz|\blsass\b|AppData[\\/](Local|Roaming)[\\/][^\n]*(Login Data|Cookies|Web Data)|\.ssh[\\/](id_|config)|\.aws[\\/]credentials|NTUSER\.DAT)"),
    ("WIN-04", "MEDIUM", "PowerShell: datu nosūtīšana (Invoke-WebRequest/RestMethod POST)",
     r"(Invoke-(WebRequest|RestMethod)|\b(iwr|irm)\b)[^\n]*(-Method\s+(Post|Put)|-Body|-InFile)"),
    ("LNX-01", "HIGH", "Linux: slepenie glabātuvi un pārlūka dati",
     r"(secret-tool\s+(lookup|search)|\.local/share/keyrings|gnome-keyring|kwallet|\.config/(google-chrome|chromium|BraveSoftware)/[^\s\"']*(Login Data|Cookies)|\.mozilla/firefox)"),
    ("SURV-01", "HIGH", "Ekrāna/tastatūras/mikrofona pārtveršana",
     r"(\bscreencapture\b|CGEventTap|\bpynput\b|keylog|AVCaptureDevice|avfoundation|x11grab|\bsox\b[^\n]*-d\b|CGWindowListCreateImage)"),
    ("SURV-02", "LOW", "Starpliktuves (clipboard) piekļuve",
     r"(\bpbpaste\b|\bpbcopy\b|NSPasteboard)"),
    ("SURV-03", "MEDIUM", "AppleScript piekļuve Mail/Messages/Contacts/Notes/Calendar",
     r"tell\s+application\s+\"(Mail|Messages|Contacts|Notes|Calendar|Reminders|Photos)\""),
    ("SURV-05", "LOW", "AppleScript piekļuve pārlūkam (Safari/Chrome)",
     r"tell\s+application\s+\"(Safari|Google Chrome)\""),
]
COMPILED = [(i, s, t, re.compile(p, re.I)) for i, s, t, p in RULES]

RE_ZEROWIDTH = re.compile("[\u200b\u200e\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069]")
RE_B64 = re.compile(r"[A-Za-z0-9+/]{240,}={0,2}")
RE_HTML_COMMENT = re.compile(r"<!--(.{40,}?)-->", re.S)
RE_URL = re.compile(r"https?://[^\s\"'<>)\]\}`\\]+", re.I)
RE_REDACT = re.compile(
    r"(sk-ant-[\w-]{6})[\w-]+|(sk-[A-Za-z0-9]{4})[A-Za-z0-9]{20,}|(ghp_[A-Za-z0-9]{4})[A-Za-z0-9]+|"
    r"(github_pat_)[\w]+|(xox[abprs]-)[\w-]+|(AKIA[0-9A-Z]{4})[0-9A-Z]+|(AIza)[0-9A-Za-z_-]+")
RE_NET_CODE = re.compile(r"\b(curl|wget|requests\.|fetch\(|urlopen|axios|http\.client|nc\s)", re.I)

TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonc", ".yml", ".yaml",
            ".toml", ".sh", ".bash", ".zsh", ".command", ".py", ".js", ".mjs",
            ".cjs", ".ts", ".rb", ".pl", ".plist", ".ini", ".cfg", ".conf", ""}
ARCHIVE_EXT = {".zip", ".skill", ".plugin", ".mcpb", ".dxt"}
SKIP_DIRS = {"node_modules", ".git", "projects", "Cache", "Code Cache",
             "GPUCache", "IndexedDB", "Local Storage", "Session Storage",
             "blob_storage", "logs", "Crashpad", "Service Worker", "sentry",
             "Partitions", "vm_bundles", "DawnCache", "shell-snapshots",
             "todos", "statsig", "ide", "telemetry", "__pycache__", ".venv",
             "venv", "site-packages", "Network", "Shared Dictionary",
             "audit-reports", "file-history", "paste-cache", "session-env",
             ".trash", ".project-cache", "outputs", "uploads"}
RE_SESSION_JSON = re.compile(r"(^|/)local_[0-9a-f-]{20,}\.json$", re.I)
RE_MINIFIED = re.compile(r"(\.min\.(js|css)|-runtime\.js)$", re.I)
SKIP_FILE_EXT = {".jsonl", ".log", ".sqlite", ".db", ".png", ".jpg", ".jpeg",
                 ".gif", ".pdf", ".docx", ".xlsx", ".pptx", ".woff", ".woff2",
                 ".ttf", ".ico", ".svg", ".map", ".lock", ".pyc"}
MAX_BYTES = 1_500_000
MAX_FILES = 30_000


@dataclass
class Finding:
    severity: str
    rule: str
    title: str
    path: str
    line: int
    snippet: str
    new: bool = False
    accepted: bool = False

    def fp(self):
        return hashlib.sha1(
            f"{self.rule}|{self.path}|{self.snippet}".encode()).hexdigest()[:16]


# ------------------------------------------------------------ palīgfunkcijas
def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def load_config():
    WORK.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2,
                                     ensure_ascii=False), encoding="utf-8")
    cfg = dict(DEFAULT_CONFIG)
    user = load_json(CONFIG, {})
    cfg.update(user)
    cfg["allowed_domains"] = sorted(set(DEFAULT_CONFIG["allowed_domains"]) | set(user.get("allowed_domains", [])))
    return cfg


def redact(s):
    return RE_REDACT.sub(lambda m: next(g for g in m.groups() if g) + "…[PASLĒPTS]", s)


def snip(s, n=170):
    s = redact(" ".join(s.strip().split()))
    return s if len(s) <= n else s[:n] + "…"


def domain_ok(host, allowed):
    host = (host or "").lower().strip(".")
    return any(host == d or host.endswith("." + d) for d in allowed)


REPO_FILES = [".claude", "CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".mcp.json",
              ".vscode/mcp.json", ".cursor", ".cursorrules", ".windsurfrules"]
REPO_SKIP = {"node_modules", "Library", "AppData", ".Trash", "venv", ".venv", "site-packages"}


def platform_dirs():
    """Claude Desktop/Cowork, IDE un pārvaldītās konfigurācijas atkarībā no OS."""
    h = HOME
    claude, ide, managed = [], [], []
    if SYS == "Darwin":
        base = h / "Library/Application Support"
        claude = [base / "Claude", base / "Claude-3p"]
        ide = [base / "Code/User", base / "Cursor/User", base / "Windsurf/User"]
        managed = [Path("/Library/Application Support/ClaudeCode")]
    elif SYS == "Windows":
        roam = Path(os.environ.get("APPDATA", h / "AppData/Roaming"))
        loc = Path(os.environ.get("LOCALAPPDATA", h / "AppData/Local"))
        pd = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
        claude = [roam / "Claude", loc / "Claude"] + \
            list((loc / "Packages").glob("Claude*/LocalCache/Roaming/Claude")) \
            if (loc / "Packages").exists() else [roam / "Claude", loc / "Claude"]
        ide = [roam / "Code/User", roam / "Cursor/User", roam / "Windsurf/User"]
        managed = [pd / "ClaudeCode"]
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", h / ".config"))
        claude = [base / "Claude", base / "claude"]
        ide = [base / "Code/User", base / "Cursor/User", base / "Windsurf/User"]
        managed = [Path("/etc/claude-code")]
    ide_files = [d / n for d in ide for n in ("mcp.json", "settings.json")]
    return claude, ide_files, managed


def find_repos(roots, depth=4):
    repos = []
    for r in roots:
        r = Path(r).expanduser()
        if not r.is_dir():
            continue
        base = len(r.parts)
        for dp, dn, fn in os.walk(r):
            if ".git" in dn or ".git" in fn:
                repos.append(Path(dp))
                dn[:] = []
                continue
            if len(Path(dp).parts) - base >= depth:
                dn[:] = []
                continue
            dn[:] = [d for d in dn if d not in REPO_SKIP and not d.startswith(".")]
    return repos


def repo_targets(repo):
    return [repo / f for f in REPO_FILES if (repo / f).exists()]


def git_toplevel(p):
    for q in [p] + list(p.parents):
        if (q / ".git").exists():
            return q
    return None


def default_targets(cfg, extra_repo_roots=()):
    claude, ide_files, managed = platform_dirs()
    sub = ["local-agent-mode-sessions", "Claude Extensions", "claude-code",
           "skills", "plugins", "claude_desktop_config.json"]
    cands = [
        HOME / ".claude/skills", HOME / ".claude/commands", HOME / ".claude/agents",
        HOME / ".claude/hooks", HOME / ".claude/plugins", HOME / ".claude/CLAUDE.md",
        HOME / ".claude/settings.json", HOME / ".claude/settings.local.json",
        HOME / ".claude.json", HOME / ".config/claude",
        HOME / ".cursor/mcp.json", HOME / ".cursor/rules",
        HOME / ".codeium/windsurf/mcp_config.json",
        *[d / x for d in claude for x in sub], *ide_files, *managed,
    ]
    targets = [c for c in cands if c.exists()]
    here = git_toplevel(Path.cwd()) or Path.cwd()
    targets += [t for t in repo_targets(here)]
    roots = [HOME / x for x in ("Documents/GitHub", "GitHub", "Developer", "Projects",
                                "projects", "code", "src", "dev", "repos", "Documents/Projects")]
    roots += [Path(x).expanduser() for x in cfg.get("repo_roots", [])] + \
             [Path(x).expanduser() for x in extra_repo_roots]
    repos = find_repos([r for r in roots if r.is_dir()])
    for r in repos:
        targets += repo_targets(r)
    return targets, len(repos)


def walk(targets, cfg):
    seen, out = set(), []
    for t in targets:
        t = Path(t).expanduser()
        if t.is_file():
            files = [t]
        else:
            files = []
            for dp, dn, fn in os.walk(t, followlinks=False):
                dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith("temp_git_")
                         and not (d == "marketplaces" and Path(dp).name == "plugins")]
                files += [Path(dp) / f for f in fn]
        for f in files:
            try:
                rp = str(f.resolve())
            except OSError:
                continue
            if rp in seen:
                continue
            seen.add(rp)
            if any(x in rp.replace("\\", "/") for x in cfg["ignore_paths"]):
                continue
            ext = f.suffix.lower()
            if ext in SKIP_FILE_EXT or RE_SESSION_JSON.search(rp.replace("\\", "/")) or RE_MINIFIED.search(rp):
                continue
            if ext not in TEXT_EXT and ext not in ARCHIVE_EXT:
                continue
            try:
                if f.stat().st_size > MAX_BYTES * (8 if ext in ARCHIVE_EXT else 1):
                    continue
            except OSError:
                continue
            out.append(f)
            if len(out) >= MAX_FILES:
                return out
    return out


def read_units(f):
    """Atgriež [(redzamais_ceļš, teksts)]; arhīviem — katru teksta failu iekšā."""
    ext = f.suffix.lower()
    if ext in ARCHIVE_EXT:
        units = []
        try:
            with zipfile.ZipFile(f) as z:
                for n in z.namelist()[:2000]:
                    e = Path(n).suffix.lower()
                    if e in TEXT_EXT and e not in SKIP_FILE_EXT:
                        info = z.getinfo(n)
                        if 0 < info.file_size <= MAX_BYTES:
                            units.append((f"{f}!/{n}",
                                          z.read(n).decode("utf-8", "replace")))
        except Exception:
            pass
        return units
    try:
        data = f.read_bytes()
        if b"\x00" in data[:4096]:
            return []
        return [(str(f), data.decode("utf-8", "replace"))]
    except OSError:
        return []


# ------------------------------------------------------------------ konteksts
RE_DOC = re.compile(r"\.(md|markdown|txt|rst)$", re.I)
RE_TEST = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures|examples?|samples?|testdata)(/|$)|\.(test|spec)\.[jt]sx?$|(^|/)test_[^/]*\.py$|_test\.(py|go|js|ts)$", re.I)
RE_INSTR = re.compile(r"(^|/)(SKILL|CLAUDE|CLAUDE\.local|AGENTS)\.md$|/(commands|agents)/[^/]+\.md$", re.I)
RE_NOISE_FILE = re.compile(r"(^|/)(LICENSE|NOTICE|COPYING)[^/]*$|package-lock\.json$|\.lock$", re.I)
# vārdi, kas rāda, ka teksts AIZSARDZĪBAI/piemēram, nevis uzbrukums
NEG_IGNORE = re.compile(r"\b(never|don'?t|do not|must not|should not|refuse|reject|untrusted|treat (it |them |this )?as (data|text)|not (a|an) (instruction|command)|attack|injection|malicious|suspicious|warn|example|e\.g\.|such as|for instance|quote|adversarial)\b", re.I)
NEG_HIDE = re.compile(r"\b(attack|injection|malicious|suspicious|warn|detect|example|e\.g\.|such as|for instance|adversarial)\b", re.I)
LADDER = {"CRITICAL": "MEDIUM", "HIGH": "LOW", "MEDIUM": None, "LOW": None}
BAD_TLD = {"py", "js", "ts", "json", "md", "sh", "txt", "yml", "yaml", "html", "css", "toml",
           "lock", "invalid", "internal", "local", "test", "localhost", "example", "mjs", "cjs",
           "tsx", "jsx", "xml", "png", "svg", "cfg", "ini"}
RE_LISTITEM = re.compile(r"^\s*([-*]\s+)?`?(Read|Edit|Write)\(//?\*\*?/[^)]*\)`?\s*,?\s*$|^\s*[\"'][^\"'\s]{2,60}[\"'],?\s*(#.*)?$")
LIST_SAFE_RULES = {"CRED-01", "CRED-03", "CRED-04", "WIN-03"}
RE_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def adjust(sev, rule, path, ctx):
    """Pielāgo smagumu pēc konteksta; None = neziņot."""
    p = path.replace("\\", "/")
    test = bool(RE_TEST.search(p))
    doc = bool(RE_DOC.search(p))
    if rule == "SECRET-01":
        return "LOW" if test else sev
    if test:
        return "LOW" if rule in ("OBF-01", "CRED-02") else None
    if rule == "INJ-01":
        if doc and not RE_INSTR.search(p):
            return LADDER[sev]
        return LADDER[sev] if NEG_IGNORE.search(ctx) else sev
    if rule.startswith("INJ-"):
        if doc and not RE_INSTR.search(p):
            return LADDER[sev]
        return LADDER[sev] if NEG_HIDE.search(ctx) else sev
    if doc:
        if RE_INSTR.search(p):   # instrukciju fails (SKILL.md u.c.): Claude to izpilda, tāpēc smagums paliek
            return LADDER[sev] if NEG_IGNORE.search(ctx) else sev
        return LADDER[sev]
    return sev


# ------------------------------------------------------------------ skenēšana
def scan_text(path, text, cfg, out):
    ign = set(cfg["ignore_rules"])
    is_md = path.lower().endswith((".md", ".markdown"))

    def add(sev, rule, title, line, sn, ctx=None):
        if rule in ign:
            return
        sev2 = adjust(sev, rule, path, ctx if ctx is not None else sn)
        if sev2:
            out.append(Finding(sev2, rule, title, path, line, snip(sn)))

    prev = ""
    for no, line in enumerate(text.splitlines(), 1):
        cur_prev, prev = prev, line
        if "audit-ignore" in line:
            continue
        long_line = len(line) > 2000          # minificēts kods: tikai nopietnie noteikumi
        L = line[:5000]
        list_item = bool(RE_LISTITEM.match(L))   # atļauju/aizliegumu vai failu nosaukumu saraksta elements
        for rid, sev, title, rx in COMPILED:
            if rid in ign or (long_line and SEV_ORDER[sev] < 3):
                continue
            if list_item and rid in LIST_SAFE_RULES:
                continue
            m = rx.search(L)
            if m:
                add(sev, rid, title, no, L[max(0, m.start() - 40):m.end() + 60],
                    ctx=cur_prev[-300:] + " " + L)

    body = text[1:] if text.startswith("﻿") else text
    m = RE_ZEROWIDTH.search(body)
    if m:
        ln = body.count("\n", 0, m.start()) + 1
        n = len(RE_ZEROWIDTH.findall(body))
        add("HIGH", "OBF-03", "Neredzamas Unicode rakstzīmes (iespējamas slēptas instrukcijas)",
            ln, f"{n} neredzamas rakstzīmes (U+{ord(m.group()):04X}…)")
    m = RE_B64.search(body)
    if m and not RE_MINIFIED.search(path):
        ln = body.count("\n", 0, m.start()) + 1
        add("MEDIUM", "OBF-04", "Garš base64 bloks (iespējami slēpti dati/kods)",
            ln, m.group()[:60] + f"… ({len(m.group())} zīmes)")
    if is_md:
        for m in RE_HTML_COMMENT.finditer(body):
            if re.search(r"\b(ignore|instruction|assistant|claude|you must|always|never|do not|system|send|https?://)", m.group(1), re.I):
                ln = body.count("\n", 0, m.start()) + 1
                add("MEDIUM", "OBF-05", "HTML komentārs ar komandām (var saturēt slēptas instrukcijas)",
                    ln, m.group(1))
                break

    # ārējie domēni: tikai kodā/konfigurācijā, nevis dokumentācijā un licencēs
    p = path.replace("\\", "/")
    if RE_DOC.search(p) or RE_TEST.search(p) or RE_NOISE_FILE.search(p):
        return
    bad = {}
    for u in RE_URL.findall(text):
        h = host_of(u)
        if not h or "$" in h or "{" in h or not RE_HOST.match(h):
            continue
        if h.rsplit(".", 1)[-1] in BAD_TLD or not h.rsplit(".", 1)[-1].isalpha():
            continue
        if not domain_ok(h, cfg["allowed_domains"]):
            bad.setdefault(h, u)
    if bad and RE_NET_CODE.search(text):
        add("MEDIUM", "NET-01", "Kods sazinās ar domēniem, kas nav atļauto sarakstā", 1,
            ", ".join(sorted(bad)[:8]) + (" …" if len(bad) > 8 else ""))
        for term in cfg["personal_terms"]:
            if term and term.lower() in text.lower():
                add("HIGH", "PRIV-01",
                    "Personas dati tajā pašā failā, kur ārējs domēns",
                    1, f"termins «{term[:3]}…» + domēni: {', '.join(sorted(bad)[:4])}")
                break


SECRETISH = re.compile(r"(key|token|secret|passw|auth|cookie|bearer)", re.I)
BROAD_PERM = re.compile(r"^(Bash|Bash\(\*\)|Bash\(\*:\*\)|Bash\((curl|wget|sh|bash|zsh|python3?|node|ssh|scp|rm|sudo|osascript)[: ]\*\)|"
                        r"WebFetch|WebFetch\(\*\)|Write|Edit|Read\(//?\*\*?\))$")
RE_MONEY_TOOL = re.compile(r"(place|submit|create|modify|cancel|replace)_?(order|trade)|(order|trade)_?(place|submit)|transfer|withdraw|payment|"
                           r"send_?(email|mail|message)|post_?message|delete|remove|(create|update)_?draft", re.I)


RE_SENS_READ = re.compile(r"^(Read|Bash)\(.*(\.ssh|\.aws|\.gnupg|\.kube|\.netrc|\.git-credentials|Keychains|Login Data|chat\.db)")


def risky_perm(a):
    a = a.strip()
    return broad_perm(a) or bool(RE_SENS_READ.match(a)) or (a.startswith("mcp__") and bool(RE_MONEY_TOOL.search(a)))


def broad_perm(a):
    a = a.strip()
    return bool(BROAD_PERM.match(a)) or (a.startswith("mcp__") and a.count("__") == 1)


def walk_cmds(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "command" and isinstance(v, str):
                acc.append(v)
            else:
                walk_cmds(v, acc)
    elif isinstance(o, list):
        for v in o:
            walk_cmds(v, acc)


def check_mcp(name, srv, path, cfg, out, where=""):
    if not isinstance(srv, dict):
        return
    tag = f"MCP «{name}»{where}"
    url = srv.get("url") or srv.get("serverUrl")
    cmd = srv.get("command")
    args = [str(a) for a in (srv.get("args") or [])]

    bundled = bool(re.search(r"/(plugins|rpm|synced|skills|marketplaces)/", path.replace("\\", "/")))

    def add(sev, rule, title, sn):
        if bundled and rule in ("MCP-01", "MCP-04", "MCP-06") and sev in ("MEDIUM", "HIGH"):
            sev = "LOW"       # spraudņa komplektā iekļauts, nav tavā aktīvajā konfigurācijā
        out.append(Finding(sev, rule, f"{tag}: {title}", path, 0, snip(sn)))

    if url:
        h = host_of(url)
        if domain_ok(h, cfg["allowed_domains"]):
            add("LOW", "MCP-01", "attālais serveris (uzticams domēns)", url)
        else:
            add("MEDIUM", "MCP-01", "attālais serveris ārpus atļauto domēnu saraksta", url)
        if url.startswith("http://") and h not in ("localhost", "127.0.0.1"):
            add("HIGH", "MCP-02", "nešifrēts savienojums (http)", url)
    if cmd:
        base = os.path.basename(cmd)
        if base in ("sh", "bash", "zsh", "dash") and ("-c" in args):
            add("HIGH", "MCP-03", "komanda tiek palaista caur shell -c", f"{cmd} {' '.join(args)}")
        if base in ("npx", "bunx", "pnpx", "uvx", "pipx"):
            pk = next((a for a in args if not a.startswith("-")), "")
            body = pk[1:] if pk.startswith("@") else pk
            pinned = ("@" in body) or ("==" in pk)
            if pk and not pinned:
                add("MEDIUM", "MCP-04",
                    "pakotne bez fiksētas versijas (supply-chain risks)", f"{base} {pk}")
        if cmd.startswith(("/tmp", "/var/tmp", "/private/tmp")) or "Downloads" in cmd:
            add("HIGH", "MCP-05", "palaiž programmu no pagaidu/lejupielāžu mapes", cmd)
        for a in args:
            if a.startswith("http"):
                h = host_of(a)
                if not domain_ok(h, cfg["allowed_domains"]):
                    add("MEDIUM", "MCP-06", "arguments satur nezināmu domēnu", a)
        for rid, sev, title, rx in COMPILED:
            if rx.search(f"{cmd} {' '.join(args)}") and rid not in cfg["ignore_rules"]:
                add(sev, rid, title, f"{cmd} {' '.join(args)}")
    env = srv.get("env") or {}
    keys = [k for k in env if SECRETISH.search(k)]
    if keys:
        add("LOW", "MCP-07", "serverim nodoti akreditācijas dati (vides mainīgie)",
            ", ".join(keys))
    hdr = srv.get("headers") or {}
    if hdr:
        add("LOW", "MCP-07", "serverim tiek sūtītas HTTP galvenes ar autorizāciju",
            ", ".join(hdr))


def check_json_structure(path, data, cfg, out):
    name = Path(path).name

    def add(sev, rule, title, sn):
        if rule not in cfg["ignore_rules"]:
            out.append(Finding(sev, rule, title, path, 0, snip(sn)))

    if not isinstance(data, dict):
        return
    # MCP serveri (arī projektu līmenī ~/.claude.json)
    for n, s in (data.get("mcpServers") or {}).items():
        check_mcp(n, s, path, cfg, out)
    for proj, pd in (data.get("projects") or {}).items():
        if isinstance(pd, dict):
            for n, s in (pd.get("mcpServers") or {}).items():
                check_mcp(n, s, path, cfg, out, f" (projekts {Path(proj).name})")
    if name.startswith("settings"):
        perm = data.get("permissions") or {}
        if perm.get("defaultMode") == "bypassPermissions":
            add("HIGH", "CFG-01", "defaultMode = bypassPermissions (visi apstiprinājumi izslēgti)", "bypassPermissions")
        for a in perm.get("allow") or []:
            if not isinstance(a, str):
                continue
            if broad_perm(a):
                add("MEDIUM", "CFG-02", "pārāk plaša atļauja bez apstiprinājuma", a)
            if RE_SENS_READ.match(a):
                add("HIGH", "CFG-09", "atļauts bez apstiprinājuma lasīt noslēpumus/privātos datus", a)
            if a.startswith("mcp__") and RE_MONEY_TOOL.search(a):
                add("HIGH", "CFG-08", "bez apstiprinājuma atļauta darbība ar naudu/sūtīšanu/dzēšanu (pārbaudi!)", a)
        if data.get("enableAllProjectMcpServers"):
            add("MEDIUM", "CFG-03", "automātiski ieslēdz visus projektu MCP serverus", "enableAllProjectMcpServers=true")
        env = data.get("env") or {}
        for k, v in env.items():
            if k in ("ANTHROPIC_BASE_URL", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                     "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL"):
                host = host_of(v) or str(v)
                if not domain_ok(host, cfg["allowed_domains"]):
                    add("HIGH", "CFG-04", "datu satiksme tiek novirzīta caur nezināmu serveri", f"{k}={v}")
            if k == "NODE_TLS_REJECT_UNAUTHORIZED" and str(v) == "0":
                add("HIGH", "CFG-05", "TLS sertifikātu pārbaude izslēgta", f"{k}=0")
        cmds = []
        walk_cmds(data.get("hooks") or {}, cmds)
        for c in cmds:
            add("MEDIUM", "HOOK-01", "Hook automātiski izpilda komandu (pārbaudi saturu)", c)
        for k in ("apiKeyHelper", "awsAuthRefresh", "awsCredentialExport"):
            if data.get(k):
                add("MEDIUM", "CFG-06", f"{k} izpilda ārēju komandu", str(data[k]))
        sl = data.get("statusLine")
        if isinstance(sl, dict) and sl.get("command"):
            add("LOW", "CFG-07", "statusLine izpilda komandu", sl["command"])


DC_CONFIGS = [".desktop-commander/config.json", ".claude-server-commander/config.json"]


def dc_installed_paths():
    """Atrod Desktop Commander paplašinājuma mapes vai konfigurācijas pieminējumus Claude Desktop konfigurācijā."""
    claude, _, _ = platform_dirs()
    found = []
    for d in claude:
        for sub in ("Claude Extensions", "Claude Extensions Settings"):
            base = d / sub
            if base.is_dir():
                found += [x for x in base.iterdir() if "desktopcommander" in x.name.lower()
                          or "desktop-commander" in x.name.lower()]
        cfgf = d / "claude_desktop_config.json"
        if cfgf.is_file():
            try:
                if re.search(r"desktop-?commander", cfgf.read_text(encoding="utf-8", errors="replace"), re.I):
                    found.append(cfgf)
            except OSError:
                pass
    return found


def dc_remote_running():
    if SYS == "Windows":
        return False
    try:
        out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False
    return any(re.search(r"desktop-commander\S*.*\sremote\b", l) and "claude_privatuma" not in l
               for l in out.splitlines())


def check_desktop_commander(cfg):
    """Desktop Commander (MCP ar pilnu failu un termināļa piekļuvi): telemetrija, mapes, attālā ierīce."""
    out = []
    if "DC-01" in cfg["ignore_rules"] and "DC-02" in cfg["ignore_rules"] and "DC-03" in cfg["ignore_rules"]:
        return out
    cfg_files = [HOME / c for c in DC_CONFIGS if (HOME / c).is_file()]
    installed = dc_installed_paths()
    device = HOME / ".desktop-commander-device" / "device.json"
    if not (cfg_files or installed or device.exists()):
        return out
    where = str(installed[0] if installed else (cfg_files[0] if cfg_files else device))

    def add(sev, rule, title, path, sn):
        if rule not in cfg["ignore_rules"]:
            out.append(Finding(sev, rule, "Desktop Commander: " + title, str(path), 0, snip(sn)))

    if cfg_files:
        c = load_json(cfg_files[0], {})
        path = cfg_files[0]
        if c.get("telemetryEnabled") is not False:
            add("MEDIUM", "DC-01", "telemetrija ieslēgta (PRIVACY.md: pēc noklusējuma ieslēgta)", path,
                f"telemetryEnabled={c.get('telemetryEnabled')!r}. Izslēgt: sarunā 'Please disable Desktop Commander telemetryEnabled in config'")
        dirs = c.get("allowedDirectories")
        if not dirs:
            add("MEDIUM", "DC-02", "allowedDirectories tukšs = piekļuve visai failu sistēmai", path,
                "ieraksti tikai vajadzīgās mapes (tas nav drošības robeža, bet samazina nejaušu piekļuvi)")
        elif any(str(d).strip() in ("/", "~", str(HOME)) for d in dirs):
            add("MEDIUM", "DC-02", "allowedDirectories ietver visu mājas mapi vai sakni", path, f"allowedDirectories={dirs}")
        if not c.get("blockedCommands"):
            add("LOW", "DC-04", "blockedCommands tukšs", path, "komandu melnais saraksts nav iestatīts")
    else:
        add("LOW", "DC-01", "konfigurācija nav atrasta, telemetriju nevar pārbaudīt (pēc noklusējuma tā ir ieslēgta)",
            where, "pārbaudi sarunā: 'Show my Desktop Commander config (get_config)'")

    if device.exists():
        add("MEDIUM", "DC-03", "attālās ierīces sesija ir uzstādīta (rīka argumenti/rezultāti tiek īslaicīgi glabāti ārējā serverī)",
            device, "ja neizmanto: npx @wonderwhy-er/desktop-commander@latest remote --logout")
    if dc_remote_running():
        add("HIGH", "DC-03", "attālais režīms PAŠLAIK DARBOJAS (komandas var pienākt no ārienes)", where,
            "aptur ar Ctrl+C tajā logā vai pabeidz procesu")
    return out


def audit(targets, cfg):
    findings, hashes = [], {}
    files = walk(targets, cfg)
    for f in files:
        units = read_units(f)
        for p, text in units:
            hashes[p] = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
            try:
                scan_text(p, text, cfg, findings)
            except Exception as e:   # viens bojāts fails neapstādina audita
                findings.append(Finding("LOW", "ERR-01", "Faila skenēšanas kļūda", p, 0, f"{type(e).__name__}: {e}"))
            if p.lower().endswith((".json", ".jsonc")):
                try:
                    check_json_structure(p, json.loads(text), cfg, findings)
                except Exception:
                    pass
    findings = [x for x in findings if not any(s in x.path.replace("\\", "/") for s in cfg["ignore_paths"])]
    return findings, hashes, len(files)


# ---------------------------------------------------------------- izvade
def active(findings):
    return [f for f in findings if not f.accepted]


def group_findings(items):
    """Apvieno vienādus (smagums, noteikums, fails) atradumus vienā ierakstā."""
    groups = {}
    for f in items:
        groups.setdefault((f.severity, f.rule, f.path), []).append(f)
    return list(groups.values())


def render_text(findings, stats, min_sev, color, show_accepted=False, detail=False):
    act = active(findings)
    pool = findings if show_accepted else act
    shown = [f for f in pool if SEV_ORDER[f.severity] >= SEV_ORDER[min_sev]]
    cnt = {k: sum(1 for f in act if f.severity == k) for k in SEV_ORDER}
    L = [f"Claude privātuma audits v{VERSION} · {stats['time']} · {socket.gethostname()} ({SYS})",
         f"Skenēti faili: {stats['files']} · repozitoriji: {stats.get('repos', 0)} · "
         f"CRITICAL {cnt['CRITICAL']} · HIGH {cnt['HIGH']} · MEDIUM {cnt['MEDIUM']} · LOW {cnt['LOW']} · "
         f"jauni: {sum(1 for f in act if f.new)} · apstiprināti: {len(findings) - len(act)}"]
    if stats.get("changed") or stats.get("removed"):
        L.append(f"Mainīti/jauni faili kopš pēdējās pārbaudes: {stats['changed']}, dzēsti: {stats['removed']}")
    for w in stats.get("warnings", []):
        L.append(("\033[1;91m" if color else "") + "⚠ " + w + (RESET if color else ""))
    if min_sev != "LOW" and cnt["LOW"]:
        L.append(f"(LOW līmeņa atradumi paslēpti; rādīt: --min-severity LOW)")
    # kopsavilkums pa noteikumiem
    by_rule = {}
    for f in shown:
        by_rule.setdefault((f.severity, f.rule, f.title), set()).add(f.path)
    if by_rule:
        L.append("\nKOPSAVILKUMS (noteikums · atradumu faili):")
        for (sev, rule, title), paths in sorted(by_rule.items(), key=lambda x: (-SEV_ORDER[x[0][0]], -len(x[1]))):
            L.append(f"  {sev:8} {rule:9} ×{len(paths):<4} {title}")
    L.append("")
    cur = None
    glist = group_findings(shown)
    glist.sort(key=lambda g: (-SEV_ORDER[g[0].severity], g[0].path, g[0].line))
    for g in glist:
        f = g[0]
        if f.severity != cur:
            cur = f.severity
            L.append((COLORS[cur] if color else "") + f"== {cur} ==" + (RESET if color else ""))
        loc = (f"{f.path}:{f.line}" if f.line else f.path).replace(str(HOME), "~")
        flags = (" [JAUNS]" if any(x.new for x in g) else "") + (" [apstiprināts]" if f.accepted else "")
        more = f" (×{len(g)} rindas)" if len(g) > 1 and not detail else ""
        L += [f"[{f.rule}] #{f.fp()}{flags} {f.title}{more}", f"    {loc}", f"    » {f.snippet}"]
        if detail:
            for x in g[1:]:
                L.append(f"    + :{x.line} » {x.snippet}")
    if not shown:
        L.append("Atradumu nav šajā smaguma līmenī. ✔")
    else:
        L.append("\nPēc pārbaudes atzīt par drošu: --accept ID (atzīst visu grupu tajā failā) vai --accept ALL")
    return "\n".join(L)


def render_md(findings, stats):
    out = [f"# Claude privātuma audits — {stats['time']}", "",
           f"Ierīce: **{socket.gethostname()}** ({SYS}) · skenēti faili: **{stats['files']}**", ""]
    for w in stats.get("warnings", []):
        out.append(f"> ⚠ {w}")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        items = sorted((f for f in findings if f.severity == sev),
                       key=lambda f: (f.path, f.line))
        out.append(f"## {sev} ({sum(1 for f in items if not f.accepted)} aktīvi)")
        for f in items:
            loc = (f"{f.path}:{f.line}" if f.line else f.path).replace(str(HOME), "~")
            tag = (" 🆕" if f.new else "") + (" ✅ apstiprināts" if f.accepted else "")
            out.append(f"- **[{f.rule}]** `#{f.fp()}`{tag} {f.title}  \n  `{loc}`  \n  `{f.snippet.replace(chr(96), chr(39))}`")
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------- paziņojumi (visas OS)
def notify(title, msg):
    try:
        with open(ALERT, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M} | {title} | {msg}\n")
    except OSError:
        pass
    try:
        if SYS == "Darwin":
            e = lambda x: x.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e",
                            f'display notification "{e(msg)}" with title "{e(title)}" sound name "Basso"'],
                           check=False, timeout=10)
        elif SYS == "Windows":
            q = lambda x: x.replace("'", "''")
            ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon=[System.Drawing.SystemIcons]::Warning;$n.Visible=$true;"
                  f"$n.ShowBalloonTip(15000,'{q(title)}','{q(msg)}',[System.Windows.Forms.ToolTipIcon]::Warning);"
                  "Start-Sleep 16;$n.Dispose()")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False, timeout=40)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "-u", "critical", title, msg], check=False, timeout=10)
    except Exception:
        pass


# ----------------------------------------------------------- grafiks (visas OS)
def file_sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def installed_script():
    return WORK / "claude_privatuma_audits.py"


def schedule_active():
    try:
        if SYS == "Darwin":
            return subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
                                  capture_output=True).returncode == 0
        if SYS == "Windows":
            return subprocess.run(["schtasks", "/Query", "/TN", WIN_TASK],
                                  capture_output=True).returncode == 0
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return CRON_MARK in r.stdout
    except Exception:
        return False


def install_schedule(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    WORK.mkdir(parents=True, exist_ok=True)
    dst = installed_script()
    if Path(__file__).resolve() != dst.resolve():
        shutil.copy2(__file__, dst)
    SCRIPT_HASH.write_text(file_sha(dst), encoding="utf-8")
    cmd = [sys.executable, str(dst), "--quiet", "--notify"]
    if SYS == "Darwin":
        plist = {"Label": LABEL, "ProgramArguments": cmd,
                 "StartCalendarInterval": {"Hour": h, "Minute": m}, "RunAtLoad": False,
                 "StandardOutPath": str(WORK / "launchd.out.log"),
                 "StandardErrorPath": str(WORK / "launchd.err.log")}
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        with open(PLIST, "wb") as fh:
            plistlib.dump(plist, fh)
        uid = os.getuid()
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(PLIST)], capture_output=True)
        r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)],
                           capture_output=True, text=True)
    elif SYS == "Windows":
        tr = " ".join(f'"{c}"' for c in cmd)
        r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", WIN_TASK,
                            "/TR", tr, "/ST", f"{h:02d}:{m:02d}"], capture_output=True, text=True)
    else:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        keep = [l for l in cur.splitlines() if CRON_MARK not in l]
        keep.append(f'{m} {h} * * * "{sys.executable}" "{dst}" --quiet --notify {CRON_MARK}')
        r = subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n",
                           capture_output=True, text=True)
    if r.returncode:
        print("Grafika izveides kļūda:", (r.stderr or r.stdout).strip())
        return 1
    print(f"Ieplānots katru dienu plkst. {h:02d}:{m:02d} ({SYS}).\nSkripts: {dst}\n"
          f"Pārskati: {REPORTS}\nPārbaude: python3 {dst} --status")
    return 0


def uninstall_schedule():
    if SYS == "Darwin":
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
        PLIST.unlink(missing_ok=True)
    elif SYS == "Windows":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", WIN_TASK], capture_output=True)
    else:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        keep = [l for l in cur.splitlines() if CRON_MARK not in l]
        subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n", text=True)
    print("Plānotais uzdevums noņemts.")
    return 0


# ------------------------------------------------------------------- kontrole
def integrity_warning():
    dst = installed_script()
    if not (dst.exists() and SCRIPT_HASH.exists()):
        return None
    if Path(__file__).resolve() != dst.resolve():
        return None
    if file_sha(dst) != SCRIPT_HASH.read_text().strip():
        return ("AUDITA SKRIPTS IR MAINĪTS kopš uzstādīšanas! Kāds (vai kāds Claude skill) to ir "
                "pārrakstījis. Pārinstalē no uzticama avota: --install-schedule")
    return None


def last_run():
    try:
        lines = RUNS.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


def log_run(entry):
    with open(RUNS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def checklist_age_days():
    d = load_json(CHECKLIST, {}).get("done")
    if not d:
        return None
    return (datetime.now() - datetime.fromisoformat(d)).days


def cmd_status(cfg):
    problems = 0
    print(f"Claude privātuma audits v{VERSION} · {socket.gethostname()} ({SYS})")
    sched = schedule_active()
    print(f"[{'OK' if sched else '!!'}] Ikdienas grafiks: {'darbojas' if sched else 'NAV UZSTĀDĪTS (--install-schedule)'}")
    problems += not sched
    w = integrity_warning()
    print(f"[{'OK' if not w else '!!'}] Skripta integritāte: {'nemainīts' if not w else w}")
    problems += bool(w)
    lr = last_run()
    if lr:
        age_h = (time.time() - lr["ts"]) / 3600
        stale = age_h > cfg["stale_hours"]
        print(f"[{'!!' if stale else 'OK'}] Pēdējā pārbaude: {lr['time']} (pirms {age_h:.0f} h)"
              + ("  ← PĀRĀK SEN, grafiks nedarbojas" if stale else ""))
        problems += stale
        print(f"     Aktīvi atradumi: CRITICAL {lr['counts']['CRITICAL']} · HIGH {lr['counts']['HIGH']} · "
              f"MEDIUM {lr['counts']['MEDIUM']} · LOW {lr['counts']['LOW']}")
        problems += lr["counts"]["CRITICAL"] + lr["counts"]["HIGH"] > 0
    else:
        print("[!!] Pārbaude vēl nav veikta."); problems += 1
    age = checklist_age_days()
    old = age is None or age > cfg["checklist_days"]
    print(f"[{'!!' if old else 'OK'}] Manuālā pārbaude (web/telefons/Connectors): "
          + ("nav veikta" if age is None else f"pirms {age} d")
          + ("  ← izpildi --checklist" if old else ""))
    problems += old
    print(f"     Apstiprināti atradumi: {len(load_json(ACCEPTED, {}))} · konfigurācija: {CONFIG}")
    print(f"     Pārskati: {REPORTS}")
    return 3 if problems else 0


def cmd_history(n=15):
    try:
        rows = [json.loads(l) for l in RUNS.read_text(encoding="utf-8").splitlines()][-n:]
    except Exception:
        print("Vēstures vēl nav."); return 0
    print(f"{'Laiks':17} {'Ierīce':16} {'Faili':>6} {'CRIT':>4} {'HIGH':>4} {'MED':>4} {'LOW':>4} {'Jauni':>5}  Skripta hash")
    for r in rows:
        c = r["counts"]
        print(f"{r['time']:17} {r['host'][:16]:16} {r['files']:>6} {c['CRITICAL']:>4} {c['HIGH']:>4} "
              f"{c['MEDIUM']:>4} {c['LOW']:>4} {r['new']:>5}  {r.get('script','')[:8]}")
    return 0


CHECKLIST_TEXT = """MANUĀLĀ PĀRBAUDE — vietas, kuras skripts nevar redzēt (ik mēnesi)
=====================================================================
1. claude.ai → Settings → Connectors / Integrations
   [ ] Katrs savienojums (Microsoft 365, Gmail, GitHub, Slack…) ir vajadzīgs; neizmantotos atvieno
   [ ] Pārbaudi piešķirtās tiesības (vai ir 'send mail', 'delete', 'write'? Vai pietiek ar lasīšanu?)
   [ ] Nepazīstami/pašpievienoti custom connectors vai MCP URL — dzēst
2. claude.ai → Settings → Capabilities / Skills
   [ ] Katrs skill (arī organizācijas) ir pazīstams; lejupielādē un pārbaudi ar --path X.skill
   [ ] Memory / Projects instrukcijas nesatur svešas komandas vai URL
3. Trešo pušu konti, kuriem Claude dod piekļuvi
   [ ] Microsoft: account.microsoft.com/privacy un myapps.microsoft.com → atļautās lietotnes
   [ ] Google: myaccount.google.com/permissions → trešo pušu piekļuve
   [ ] GitHub: github.com/settings/installations un /settings/applications → Claude lietotne,
       tiesības tikai vajadzīgajiem repozitorijiem
4. Claude Code tīmekļa/mākoņa sesijas (claude.ai/code)
   [ ] Environments: tīkla režīms, atļautie hosti, vides mainīgie, setup skripts — bez noslēpumiem un liekām piekļuvēm
   [ ] Repozitoriju .claude/settings.json hooks (skripts tos pārbauda, ja repo ir klonēts, vai: --git URL)
5. Mobilās lietotnes (iPhone/iPad/Android)
   [ ] Lokāli nav ko skenēt: tās izmanto to pašu kontu un savienojumus kā web (sk. 1.–2. punktu)
   [ ] Atver kopīgotās saites un artefaktus: Settings → pārbaudi, kas ir publiski/kopīgots
6. Citas ierīces
   [ ] Skripts uzstādīts un darbojas katrā datorā (python3 ... --status katrā)
Kad pabeigts: python3 claude_privatuma_audits.py --checklist-done
"""


def clone_repo(url):
    d = tempfile.mkdtemp(prefix="claude_audit_")
    r = subprocess.run(["git", "clone", "--depth", "1", "--no-recurse-submodules", url, d],
                       capture_output=True, text=True)
    if r.returncode:
        print("git clone kļūda:", r.stderr.strip()); shutil.rmtree(d, ignore_errors=True)
        return None
    return d


def cmd_accept(ids, findings, unaccept=False):
    acc = load_json(ACCEPTED, {})
    if "ALL" in ids:
        chosen = findings
    else:
        keys = {(f.rule, f.path) for f in findings if f.fp() in ids}
        chosen = [f for f in findings if f.fp() in ids or (f.rule, f.path) in keys]
    if not chosen and not unaccept:
        print("Neviens atradums neatbilst norādītajiem ID."); return 1
    for f in chosen:
        acc[f.fp()] = {"rule": f.rule, "path": f.path, "snippet": f.snippet,
                       "date": datetime.now().strftime("%Y-%m-%d")}
    if unaccept:
        for i in ids:
            acc.pop(i, None)
    ACCEPTED.write_text(json.dumps(acc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(("Noņemti" if unaccept else "Apstiprināti") + f" {len(ids) if unaccept else len(chosen)} atradumi. "
          "Ja faila saturs mainīsies, atradums parādīsies atkal.")
    return 0


def cmd_fix_permissions(cfg, extra_repos, yes, paths=()):
    """Pārvieto riskantās atļaujas no 'allow' uz 'ask': Claude turpmāk vienmēr jautās pirms palaišanas."""
    targets, _ = default_targets(cfg, extra_repos)
    targets = list(targets) + [Path(x).expanduser() for x in paths]
    files = [f for f in walk(targets, cfg)
             if f.name in ("settings.json", "settings.local.json") and ".claude" in f.parts
             and not ({"plugins", "rpm", "skills", "marketplaces", "synced"} & set(f.parts))]
    changed = 0
    for f in sorted(set(files)):
        data = load_json(f, None)
        if not isinstance(data, dict):
            continue
        perm = data.get("permissions")
        allow = perm.get("allow") if isinstance(perm, dict) else None
        if not isinstance(allow, list):
            continue
        risky = [a for a in allow if isinstance(a, str) and risky_perm(a)]
        if not risky:
            continue
        print(f"\n{str(f).replace(str(HOME), '~')}")
        for a in risky:
            print(f"    {a}")
        if not yes:
            try:
                ans = input("  Pārvietot uz 'ask' (Claude vienmēr jautās)? [j/N] ").strip().lower()
            except EOFError:
                ans = ""
            if ans not in ("j", "y", "jā", "ja", "yes"):
                print("  izlaists")
                continue
        backup = f.with_name(f.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(f, backup)
        ask = perm.get("ask") if isinstance(perm.get("ask"), list) else []
        perm["allow"] = [a for a in allow if a not in risky]
        perm["ask"] = ask + [a for a in risky if a not in ask]
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, f)
        changed += 1
        print(f"  ✔ pārvietots uz 'ask'. Rezerves kopija: {backup.name}")
    print(f"\nLaboti faili: {changed}. Atcelt: atjauno failu no .bak-… kopijas." if changed
          else "\nNav ko labot: riskantu atļauju sarakstā 'allow' nav.")
    return 0


def claude_running():
    if SYS != "Darwin":
        return False
    try:
        return subprocess.run(["pgrep", "-x", "Claude"], capture_output=True).returncode == 0
    except Exception:
        return False


def quit_claude(timeout=25):
    """Korekti aizver Claude Desktop (macOS) un gaida, līdz process beidzas."""
    try:
        subprocess.run(["osascript", "-e", 'tell application "Claude" to quit'], capture_output=True, timeout=15)
    except Exception:
        pass
    for _ in range(timeout):
        if not claude_running():
            return True
        time.sleep(1)
    return not claude_running()


def fix_desktop_commander(cfg_path):
    """telemetryEnabled=false; allowedDirectories = esošās + tavas darba mapes, kas pastāv. Ar rezerves kopiju."""
    c = load_json(cfg_path, None)
    if not isinstance(c, dict):
        print(f"  ! Desktop Commander konfigurāciju neizdevās nolasīt: {cfg_path}")
        return False
    backup = cfg_path.with_name(cfg_path.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(cfg_path, backup)
    wanted = [str(HOME / "Developer"), str(HOME / "Documents" / "LSB")]
    dirs = list(c.get("allowedDirectories") or [])
    for d in wanted:
        if Path(d).is_dir() and d not in dirs:
            dirs.append(d)
    c["telemetryEnabled"] = False
    c["allowedDirectories"] = dirs
    tmp = cfg_path.with_name(cfg_path.name + ".tmp")
    tmp.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, cfg_path)
    chk = load_json(cfg_path, {})
    ok = chk.get("telemetryEnabled") is False and bool(chk.get("allowedDirectories"))
    print(f"  {'✔' if ok else '!'} telemetrija izslēgta; atļautās mapes: {', '.join(chk.get('allowedDirectories') or ['(nav)']).replace(str(HOME), '~')}")
    print(f"    rezerves kopija: {backup.name}")
    return ok


def cmd_fix_all(cfg, extra_repos, yes):
    """Viss vienā reizē: aizver Claude, sakārto atļaujas un Desktop Commander, atver Claude, parāda rezultātu."""
    print("Šī komanda:\n  1) aizvērs Claude Desktop (ja darbojas) un pēc tam to atkal atvērs;\n"
          "  2) riskantās atļaujas pārvietos uz 'ask' (Claude vienmēr jautās);\n"
          "  3) Desktop Commander: izslēgs telemetriju un ierobežos mapes uz ~/Developer un ~/Documents/LSB.\n"
          "Pirms katras izmaiņas tiek izveidota rezerves kopija (.bak-…).")
    if not yes:
        try:
            ans = input("\nTurpināt? [j/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("j", "y", "jā", "ja", "yes"):
            print("Atcelts. Nekas netika mainīts.")
            return 0
    was_running = claude_running()
    if was_running:
        print("\n• Aizver Claude Desktop…")
        if not quit_claude():
            print("  ! Claude Desktop neaizvērās. Aizver to ar Cmd+Q un palaid komandu vēlreiz. Nekas netika mainīts.")
            return 1
        print("  ✔ aizvērts")
    print("\n• Atļaujas:")
    cmd_fix_permissions(cfg, extra_repos, True)
    print("\n• Desktop Commander:")
    cf = [HOME / c for c in DC_CONFIGS if (HOME / c).is_file()]
    if cf:
        fix_desktop_commander(cf[0])
    else:
        print("  (konfigurācijas fails nav atrasts, izlaists)")
    if was_running and SYS == "Darwin":
        print("\n• Atver Claude Desktop atkal…")
        subprocess.run(["open", "-a", "Claude"], capture_output=True)
    print("\n== REZULTĀTS ==")
    dc = [f for f in check_desktop_commander(cfg) if f.severity in ("MEDIUM", "HIGH")]
    targets, _ = default_targets(cfg, extra_repos)
    left = 0
    for f in walk(targets, cfg):
        if f.name in ("settings.json", "settings.local.json") and ".claude" in f.parts \
                and not ({"plugins", "rpm", "skills", "marketplaces", "synced"} & set(f.parts)):
            d = load_json(f, {})
            al = ((d.get("permissions") or {}).get("allow") if isinstance(d, dict) else None) or []
            left += sum(1 for a in al if isinstance(a, str) and risky_perm(a))
    print(f"  Desktop Commander atlikušie MEDIUM/HIGH atradumi: {len(dc)}")
    print(f"  Riskantas atļaujas sarakstā 'allow': {left}")
    if not dc and not left:
        print("\n✔ VISS SAKĀRTOTS.")
        return 0
    for f in dc:
        print(f"  - {f.title}")
    print("\n! Daļa nav sakārtota (sk. augstāk).")
    return 1


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Claude privātuma audits")
    ap.add_argument("--path", action="append", default=[], help="papildu fails/mape/.skill/.zip")
    ap.add_argument("--repos", action="append", default=[], help="papildu mape ar git repozitorijiem")
    ap.add_argument("--git", action="append", default=[], help="attāla repozitorija URL (shallow clone)")
    ap.add_argument("--no-default", action="store_true", help="neskenēt standarta vietas")
    ap.add_argument("--min-severity", default="MEDIUM", choices=list(SEV_ORDER))
    ap.add_argument("--detail", action="store_true", help="rādīt katru rindu atsevišķi")
    ap.add_argument("--show-accepted", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--install-schedule", action="store_true")
    ap.add_argument("--uninstall-schedule", action="store_true")
    ap.add_argument("--time", default="09:07", help="ikdienas palaišanas laiks HH:MM")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--checklist", action="store_true")
    ap.add_argument("--checklist-done", action="store_true")
    ap.add_argument("--accept", nargs="+", metavar="ID")
    ap.add_argument("--unaccept", nargs="+", metavar="ID")
    ap.add_argument("--fix-permissions", action="store_true",
                    help="riskantās atļaujas no 'allow' pārvieto uz 'ask' (ar rezerves kopiju)")
    ap.add_argument("--yes", action="store_true", help="--fix-permissions/--fix-all bez jautājumiem")
    ap.add_argument("--fix-all", action="store_true",
                    help="viss vienā reizē: atļaujas + Desktop Commander (aizver un atkal atver Claude Desktop)")
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args()

    cfg = load_config()
    if a.install_schedule:
        return install_schedule(a.time)
    if a.uninstall_schedule:
        return uninstall_schedule()
    if a.fix_all:
        return cmd_fix_all(cfg, a.repos, a.yes)
    if a.fix_permissions:
        return cmd_fix_permissions(cfg, a.repos, a.yes, a.path)
    if a.status:
        return cmd_status(cfg)
    if a.history:
        return cmd_history()
    if a.checklist:
        print(CHECKLIST_TEXT); return 0
    if a.checklist_done:
        CHECKLIST.write_text(json.dumps({"done": datetime.now().isoformat()}))
        print("Manuālā pārbaude atzīmēta kā veikta."); return 0
    if a.unaccept:
        return cmd_accept(a.unaccept, [], unaccept=True)

    targets, nrepos = ([], 0) if a.no_default else default_targets(cfg, a.repos)
    targets += [Path(p).expanduser() for p in a.path + cfg["extra_paths"]]
    for r in find_repos([Path(x).expanduser() for x in a.repos]) if a.no_default else []:
        targets += repo_targets(r); nrepos += 1
    clones = {}
    for url in a.git:
        d = clone_repo(url)
        if d:
            clones[d] = url
            targets.append(Path(d))
    if not targets and a.no_default:
        print("Nav ko skenēt: nav atrasta neviena Claude mape. Izmanto --path vai --repos.")
        return 0

    findings, hashes, nfiles = audit(targets, cfg)
    if not a.no_default:
        findings += check_desktop_commander(cfg)
    for d, url in clones.items():
        for f in findings:
            f.path = f.path.replace(d, url)
        hashes = {k.replace(d, url): v for k, v in hashes.items()}
        shutil.rmtree(d, ignore_errors=True)

    acc = load_json(ACCEPTED, {})
    for f in findings:
        f.accepted = f.fp() in acc
    if a.accept:
        return cmd_accept(a.accept, findings)

    prev = load_json(STATE, {})
    known = set(prev.get("findings", []))
    old_hash = prev.get("hashes", {})
    first_run = not prev
    partial = bool(a.path or a.git or a.no_default)   # daļēja pārbaude nepārraksta pilno bāzlīniju
    for f in findings:
        f.new = (not first_run) and (not partial) and f.fp() not in known
    changed = [p for p, h in hashes.items() if old_hash.get(p) != h] if not (first_run or partial) else []
    removed = [p for p in old_hash if p not in hashes] if not (first_run or partial) else []
    warnings = []
    w = integrity_warning()
    if w:
        warnings.append(w)
    lr = last_run()
    if lr and (time.time() - lr["ts"]) / 3600 > cfg["stale_hours"] * 1.5 and a.quiet:
        warnings.append(f"Iepriekšējā pārbaude bija {lr['time']} — grafiks laikam nedarbojās.")
    age = checklist_age_days()
    if age is None or age > cfg["checklist_days"]:
        warnings.append("Manuālā pārbaude (web/telefons/Connectors) nav veikta — palaid --checklist.")
    stats = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "files": nfiles,
             "repos": nrepos, "changed": len(changed), "removed": len(removed), "warnings": warnings}

    act = active(findings)
    counts = {k: sum(1 for f in act if f.severity == k) for k in SEV_ORDER}
    serious = [f for f in act if SEV_ORDER[f.severity] >= 3]
    new_serious = [f for f in serious if f.new or first_run]

    if not a.no_save:
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        (REPORTS / f"{stamp}.md").write_text(render_md(findings, stats), encoding="utf-8")
        (REPORTS / "pedejais.json").write_text(
            json.dumps({"stats": stats, "findings": [dict(asdict(f), id=f.fp()) for f in findings]},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        if not partial:
            tmp = STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"findings": [f.fp() for f in findings],
                                       "hashes": hashes}), encoding="utf-8")
            os.replace(tmp, STATE)
            log_run({"ts": time.time(), "time": stats["time"], "host": socket.gethostname(),
                     "os": SYS, "files": nfiles, "counts": counts, "new": sum(f.new for f in act),
                     "script": file_sha(__file__)[:16], "version": VERSION})
        for old in sorted(REPORTS.glob("20*.md"))[:-60]:
            old.unlink(missing_ok=True)

    if not a.quiet:
        if a.json:
            print(json.dumps({"stats": stats, "findings": [dict(asdict(f), id=f.fp()) for f in findings]},
                             ensure_ascii=False, indent=2))
        else:
            print(render_text(findings, stats, a.min_severity, sys.stdout.isatty(), a.show_accepted, a.detail))
            if not a.no_save:
                print(f"\nPilns pārskats: {REPORTS}")
    if a.notify and (new_serious or w):
        notify("Claude privātuma audits",
               (w or f"{len(new_serious)} nopietni atradumi (HIGH/CRITICAL). Pirmais: {new_serious[0].title}"))
    if serious:
        return 2
    return 1 if counts["MEDIUM"] else 0


if __name__ == "__main__":
    sys.exit(main())
