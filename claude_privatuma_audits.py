#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude privātuma audits (macOS)
================================
Pārbauda visus lokāli pieejamos Claude skill, aģentus, komandas, instrukcijas
(CLAUDE.md), hooks, atļaujas un MCP savienojumus uz komandām un tekstiem, kas
var apdraudēt privātumu: datu nosūtīšana ārpus datora, paroļu/atslēgu/pārlūka
datu lasīšana, slēptas instrukcijas, aizmiglots kods, pastāvīga ievietošanās
sistēmā, atļauju apiešana u.c.

Lietošana:
    python3 claude_privatuma_audits.py                 # vienreizēja pārbaude
    python3 claude_privatuma_audits.py --notify        # + macOS paziņojums
    python3 claude_privatuma_audits.py --install-schedule [--time 09:07]
    python3 claude_privatuma_audits.py --uninstall-schedule
    python3 claude_privatuma_audits.py --path ~/Downloads/jauns.skill
    python3 claude_privatuma_audits.py --json          # JSON izvade
    python3 claude_privatuma_audits.py --min-severity MEDIUM

Atgriezes kods: 0 = tīrs/LOW, 1 = ir MEDIUM, 2 = ir HIGH/CRITICAL.
Konfigurācija: ~/.claude-audit/config.json (tiek izveidota pirmajā palaišanā).
Rindu var atzīmēt kā drošu, pievienojot tai komentāru: audit-ignore

Ierobežojums: skripts redz tikai to, kas ir glabāts šajā datorā. claude.ai
tīmekļa savienojumi (Connectors) un organizācijas skill, kas nav sinhronizēti
uz Mac, jāpārbauda claude.ai Settings; eksportētu skill (.zip/.skill) var
pārbaudīt ar --path.
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

HOME = Path.home()
WORK = HOME / ".claude-audit"
CONFIG = WORK / "config.json"
STATE = WORK / "state.json"
REPORTS = WORK / "reports"
LABEL = "lv.lsb.claude-privatuma-audits"
PLIST = HOME / "Library/LaunchAgents" / f"{LABEL}.plist"

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
        "localhost", "127.0.0.1", "likumi.lv", "mk.gov.lv", "vm.gov.lv",
        "nvd.gov.lv", "spkc.gov.lv", "lsb.lv", "saeima.lv", "wikipedia.org",
    ],
    "personal_terms": [],          # piem. e-pasts, tālrunis, personas kods
    "ignore_rules": [],            # piem. ["OBF-02"]
    "ignore_paths": [],            # apakšvirknes, piem. ["/node_modules/"]
    "extra_paths": [],             # papildu mapes/faili, ko skenēt vienmēr
}

# ---------------------------------------------------------------- noteikumi
# (id, smagums, nosaukums, regex)
RULES = [
    ("EXFIL-01", "HIGH", "Datu nosūtīšana ar curl/wget",
     r"\b(curl|wget)\b[^\n]*(\s-d\b|--data|--data-binary|--data-raw|\s-F\b|--form|\s-T\b|--upload-file|-X\s*(POST|PUT)|--post-)"),
    ("EXFIL-02", "HIGH", "Zināms datu savākšanas/webhook pakalpojums",
     r"(discord(app)?\.com/api/webhooks|hooks\.slack\.com|webhook\.site|requestbin|pipedream\.net|ngrok(-free)?\.(io|app|dev)|transfer\.sh|pastebin\.com|paste\.ee|0x0\.st|file\.io|interact\.sh|oast\.(pro|live|site|online|fun|me)|trycloudflare\.com|api\.telegram\.org/bot|burpcollaborator)"),
    ("EXFIL-03", "HIGH", "Tiešs tīkla savienojums (nc/ncat/dev/tcp)",
     r"(\b(nc|ncat|netcat)\s+(-\w+\s+)*[\w.-]+\s+\d{2,5}\b|/dev/(tcp|udp)/)"),
    ("EXFIL-04", "MEDIUM", "Failu pārsūtīšana uz attālu serveri (scp/rsync/sftp)",
     r"\b(scp|rsync|sftp)\b[^\n]*\s[\w.-]+@[\w.-]+:"),
    ("EXFIL-05", "MEDIUM", "HTTP POST/PUT no koda",
     r"(requests\.(post|put)\(|httpx\.(post|put)\(|urllib\.request\.urlopen\(|method\s*[:=]\s*['\"](POST|PUT)['\"]|XMLHttpRequest|navigator\.sendBeacon)"),
    ("CRED-01", "HIGH", "Piekļuve atslēgām/akreditācijas datiem (.ssh, .aws, .kube, .netrc…)",
     r"(\.ssh/(id_|config|known_hosts|authorized_keys)|\.aws/(credentials|config)|\.gnupg\b|\.kube/config|\.netrc\b|\.docker/config\.json|\.npmrc\b|\.pypirc\b|\.git-credentials|\.config/gh/hosts)"),
    ("CRED-02", "CRITICAL", "Piekļuve macOS Keychain",
     r"(\bsecurity\s+(find|dump|export|add)-?(generic|internet|keychain|identity)?[- ]?(password|keychain)?\b[^\n]*(-w|-s|dump)|Library/Keychains|login\.keychain|security\s+dump-keychain)"),
    ("CRED-03", "HIGH", "Pārlūka dati (paroles, sīkdatnes, vēsture)",
     r"(Chrome/[^\s\"']*(Login Data|Cookies|Web Data|History)|Firefox/Profiles|cookies\.sqlite|logins\.json|Safari/(Cookies|History|LastSession)|Library/Cookies|Brave-Browser|Microsoft Edge/Default)"),
    ("CRED-04", "HIGH", "Personiskie dati: Messages/Mail/Kontakti/Piezīmes/TCC",
     r"(Library/Messages|chat\.db\b|Library/Mail\b|AddressBook|NoteStore\.sqlite|com\.apple\.TCC|TCC\.db|Library/Calendars)"),
    ("CRED-05", "MEDIUM", "Vides mainīgo (slepeno atslēgu) izvilkšana",
     r"(\bprintenv\b|\benv\s*\||\benv\s*>|os\.environ(\.copy\(\)|\.items\(\))|JSON\.stringify\(process\.env\)|\bset\s*\|\s*(curl|nc))"),
    ("CRED-06", "MEDIUM", ".env faila lasīšana",
     r"\b(cat|less|more|head|tail|source|open|read)\b[^\n]*\s[\w./~-]*\.env\b"),
    ("SECRET-01", "HIGH", "Failā cieti ierakstīta slepenā atslēga/token",
     r"(sk-ant-[\w-]{20,}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{30,}|github_pat_[\w]{30,}|xox[abprs]-[\w-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)"),
    ("INJ-01", "HIGH", "Instrukciju ignorēšana (prompt injection)",
     r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)*(previous|prior|above|earlier|system|safety)\s+(instructions|rules|prompts?|guidelines|messages)"),
    ("INJ-02", "HIGH", "Prasība slēpt darbības no lietotāja",
     r"((do not|don'?t|never|must not)\s+(tell|inform|mention|reveal|show|notify|disclose|alert)[^\n]{0,40}(user|human|person)|without\s+(telling|informing|notifying|alerting)\s+the\s+user|hide\s+this\s+from|keep\s+this\s+(secret|hidden|confidential)\s+from|nesaki\s+lietotājam|neinformē\s+lietotāj)"),
    ("INJ-03", "MEDIUM", "Slepenas/fona darbības formulējums",
     r"\b(silently|secretly|covertly|stealthily|quietly\s+(send|upload|post|copy))\b"),
    ("INJ-04", "HIGH", "Prasība sūtīt sarunu/atmiņu/personas datus uz ārieni",
     r"(send|upload|post|forward|exfiltrate|transmit|leak)[^\n]{0,60}(conversation|chat history|memory|memories|user'?s? (data|files|email|name|contacts|documents)|system prompt|credentials|api[ _-]?keys?|passwords?)[^\n]{0,80}(to\s+https?://|to\s+(the\s+)?(server|endpoint|url|webhook|address)|via\s+(http|email))"),
    ("INJ-05", "HIGH", "Drošības/atļauju apiešanas karodziņi",
     r"(--dangerously-skip-permissions|bypassPermissions|dangerouslyDisableSandbox|--no-verify-ssl|NODE_TLS_REJECT_UNAUTHORIZED\s*[=:]\s*['\"]?0|curl\s[^\n]*\s(-k|--insecure)\b)"),
    ("INJ-06", "MEDIUM", "Aicinājums izslēgt apstiprinājumus/drošību",
     r"(disable\s+(the\s+)?(sandbox|permission|safety|confirmation)|skip\s+(the\s+)?(permission|confirmation|approval)|without\s+(asking|confirmation|permission|approval)|never\s+ask\s+(the\s+user\s+)?(for\s+)?(confirmation|permission))"),
    ("OBF-01", "CRITICAL", "Attālā koda lejupielāde un izpilde / base64 izpilde",
     r"((curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b|base64\s+(-d|-D|--decode)[^\n]*\|\s*(sudo\s+)?(ba|z)?sh\b|eval\s*\(?\s*\"?\$\(\s*(curl|wget)|python3?\s+-c\s+[^\n]*(exec|b64decode|urlopen)|(bash|sh)\s+<\(\s*(curl|wget))"),
    ("OBF-02", "MEDIUM", "Dinamiska koda izpilde / dekodēšana (eval, exec, atob…)",
     r"(\beval\s*[\(\$\"']|\bexec\s*\(|base64\.b64decode|\batob\(|String\.fromCharCode|new Function\(|(\\x[0-9a-fA-F]{2}){8,})"),
    ("PERS-01", "HIGH", "Pastāvīga ievietošanās (launchd/cron/login items)",
     r"(launchctl\s+(load|bootstrap|submit|enable)|Library/LaunchAgents|Library/LaunchDaemons|\bcrontab\s+(-|\S)|/etc/cron|osascript[^\n]*login item|sfltool|systemctl\s+enable)"),
    ("PERS-02", "HIGH", "Shell profila (.zshrc/.bashrc…) modificēšana",
     r"((>>?|tee\s+-a)\s*~?/?[\w./-]*\.(zshrc|zshenv|zprofile|bashrc|bash_profile|profile)\b|sed\s+-i[^\n]*\.(zshrc|zshenv|zprofile|bashrc|bash_profile))"),
    ("PERS-03", "MEDIUM", "Claude iestatījumu/instrukciju modificēšana no skripta",
     r"((>>?|tee(\s+-a)?|sed\s+-i|mv|cp)\s+[^\n]*\.claude/(settings|CLAUDE|hooks|skills|agents)|(>>?|tee)\s*[^\n]*\.claude\.json)"),
    ("SURV-01", "HIGH", "Ekrāna/tastatūras/mikrofona pārtveršana",
     r"(\bscreencapture\b|CGEventTap|\bpynput\b|keylog|AVCaptureDevice|avfoundation|x11grab|\bsox\b[^\n]*-d\b|CGWindowListCreateImage)"),
    ("SURV-02", "MEDIUM", "Starpliktuves (clipboard) piekļuve",
     r"(\bpbpaste\b|\bpbcopy\b|NSPasteboard|navigator\.clipboard)"),
    ("SURV-03", "MEDIUM", "AppleScript piekļuve Mail/Messages/Contacts/Notes/Calendar",
     r"tell\s+application\s+\"(Mail|Messages|Contacts|Notes|Calendar|Reminders|Photos|Safari|Google Chrome)\""),
    ("SURV-04", "LOW", "osascript / System Events izmantošana",
     r"\b(osascript|System Events)\b"),
]
COMPILED = [(i, s, t, re.compile(p, re.I)) for i, s, t, p in RULES]

RE_ZEROWIDTH = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩]")
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
SKIP_DIRS = {"node_modules", ".git", "projects", "cache", "Cache", "Code Cache",
             "GPUCache", "IndexedDB", "Local Storage", "Session Storage",
             "blob_storage", "logs", "Crashpad", "Service Worker", "sentry",
             "Partitions", "vm_bundles", "DawnCache", "shell-snapshots",
             "todos", "statsig", "ide", "telemetry", "__pycache__", ".venv",
             "venv", "site-packages", "Network", "Shared Dictionary",
             "audit-reports", "file-history", "paste-cache", "session-env"}
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
    cfg.update(load_json(CONFIG, {}))
    return cfg


def redact(s):
    return RE_REDACT.sub(lambda m: next(g for g in m.groups() if g) + "…[PASLĒPTS]", s)


def snip(s, n=170):
    s = redact(" ".join(s.strip().split()))
    return s if len(s) <= n else s[:n] + "…"


def domain_ok(host, allowed):
    host = (host or "").lower().strip(".")
    return any(host == d or host.endswith("." + d) for d in allowed)


def default_targets():
    L = HOME / "Library/Application Support"
    cands = [
        HOME / ".claude/skills", HOME / ".claude/commands",
        HOME / ".claude/agents", HOME / ".claude/hooks",
        HOME / ".claude/plugins", HOME / ".claude/CLAUDE.md",
        HOME / ".claude/settings.json", HOME / ".claude/settings.local.json",
        HOME / ".claude.json", HOME / ".config/claude",
        L / "Claude/claude_desktop_config.json",
        L / "Claude/local-agent-mode-sessions",
        L / "Claude/Claude Extensions", L / "Claude/claude-code",
        L / "Claude/skills", L / "Claude/plugins",
        HOME / "Library/Application Support/Claude-3p",
        Path.cwd() / ".claude", Path.cwd() / "CLAUDE.md", Path.cwd() / ".mcp.json",
    ]
    return [c for c in cands if c.exists()]


def walk(targets, cfg):
    seen, out = set(), []
    for t in targets:
        t = Path(t).expanduser()
        if t.is_file():
            files = [t]
        else:
            files = []
            for dp, dn, fn in os.walk(t, followlinks=False):
                dn[:] = [d for d in dn if d not in SKIP_DIRS]
                files += [Path(dp) / f for f in fn]
        for f in files:
            try:
                rp = str(f.resolve())
            except OSError:
                continue
            if rp in seen:
                continue
            seen.add(rp)
            if any(x in rp for x in cfg["ignore_paths"]):
                continue
            ext = f.suffix.lower()
            if ext in SKIP_FILE_EXT:
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


# ------------------------------------------------------------------ skenēšana
def scan_text(path, text, cfg, out):
    ign = set(cfg["ignore_rules"])
    is_md = path.lower().endswith((".md", ".markdown"))

    def add(sev, rule, title, line, sn):
        if rule not in ign:
            out.append(Finding(sev, rule, title, path, line, snip(sn)))

    for no, line in enumerate(text.splitlines(), 1):
        if "audit-ignore" in line:
            continue
        L = line[:5000]
        for rid, sev, title, rx in COMPILED:
            if rid in ign:
                continue
            m = rx.search(L)
            if m:
                add(sev, rid, title, no, L[max(0, m.start() - 40):m.end() + 60])

    body = text[1:] if text.startswith("﻿") else text
    m = RE_ZEROWIDTH.search(body)
    if m:
        ln = body.count("\n", 0, m.start()) + 1
        n = len(RE_ZEROWIDTH.findall(body))
        add("HIGH", "OBF-03", "Neredzamas Unicode rakstzīmes (iespējamas slēptas instrukcijas)",
            ln, f"{n} neredzamas rakstzīmes (U+{ord(m.group()):04X}…)")
    m = RE_B64.search(body)
    if m:
        ln = body.count("\n", 0, m.start()) + 1
        add("MEDIUM", "OBF-04", "Garš base64 bloks (iespējami slēpti dati/kods)",
            ln, m.group()[:60] + f"… ({len(m.group())} zīmes)")
    if is_md:
        for m in RE_HTML_COMMENT.finditer(body):
            ln = body.count("\n", 0, m.start()) + 1
            add("MEDIUM", "OBF-05", "HTML komentārs ar saturu (var saturēt slēptas instrukcijas)",
                ln, m.group(1))
            break

    # domēni
    urls = RE_URL.findall(text)
    bad = {}
    for u in urls:
        h = urlparse(u).hostname
        if h and not domain_ok(h, cfg["allowed_domains"]) and "$" not in h and "{" not in h:
            bad.setdefault(h, u)
    if bad:
        sev = "MEDIUM" if RE_NET_CODE.search(text) else "LOW"
        add(sev, "NET-01", "Nezināmi ārējie domēni (nav atļauto sarakstā)", 1,
            ", ".join(sorted(bad)[:8]) + (" …" if len(bad) > 8 else ""))
        for term in cfg["personal_terms"]:
            if term and term.lower() in text.lower():
                add("HIGH", "PRIV-01",
                    "Personas dati tajā pašā failā, kur ārējs domēns",
                    1, f"termins «{term[:3]}…» + domēni: {', '.join(sorted(bad)[:4])}")
                break


SECRETISH = re.compile(r"(key|token|secret|passw|auth|cookie|bearer)", re.I)
BROAD_PERM = re.compile(r"^(Bash|Bash\(\*\)|Bash\(\*:\*\)|Bash\(curl[^)]*\)|Bash\(wget[^)]*\)|"
                        r"Bash\(sh[^)]*\)|Bash\(bash[^)]*\)|WebFetch|WebFetch\(\*\)|"
                        r"Write|Edit|Read\(//?\*\*?\)|mcp__\w+)$")


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

    def add(sev, rule, title, sn):
        out.append(Finding(sev, rule, f"{tag}: {title}", path, 0, snip(sn)))

    if url:
        h = urlparse(url).hostname
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
                h = urlparse(a).hostname
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
            if isinstance(a, str) and BROAD_PERM.match(a.strip()):
                add("MEDIUM", "CFG-02", "pārāk plaša atļauja bez apstiprinājuma", a)
        if data.get("enableAllProjectMcpServers"):
            add("MEDIUM", "CFG-03", "automātiski ieslēdz visus projektu MCP serverus", "enableAllProjectMcpServers=true")
        env = data.get("env") or {}
        for k, v in env.items():
            if k in ("ANTHROPIC_BASE_URL", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                     "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL"):
                host = urlparse(str(v)).hostname or str(v)
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


def audit(targets, cfg):
    findings, hashes = [], {}
    files = walk(targets, cfg)
    for f in files:
        units = read_units(f)
        for p, text in units:
            hashes[p] = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
            scan_text(p, text, cfg, findings)
            if p.lower().endswith((".json", ".jsonc")):
                try:
                    check_json_structure(p, json.loads(text), cfg, findings)
                except Exception:
                    pass
    findings = [x for x in findings if not any(s in x.path for s in cfg["ignore_paths"])]
    return findings, hashes, len(files)


# ---------------------------------------------------------------- izvade
def render_text(findings, stats, min_sev, color):
    shown = [f for f in findings if SEV_ORDER[f.severity] >= SEV_ORDER[min_sev]]
    shown.sort(key=lambda f: (-SEV_ORDER[f.severity], f.path, f.line))
    lines = []
    cnt = {s: sum(1 for f in findings if f.severity == s) for s in SEV_ORDER}
    lines.append(f"Claude privātuma audits · {stats['time']}")
    lines.append(f"Skenēti faili: {stats['files']} · CRITICAL {cnt['CRITICAL']} · "
                 f"HIGH {cnt['HIGH']} · MEDIUM {cnt['MEDIUM']} · LOW {cnt['LOW']} · "
                 f"jauni kopš pēdējās reizes: {sum(1 for f in findings if f.new)}")
    if stats.get("changed"):
        lines.append(f"Mainīti/jauni faili kopš pēdējās pārbaudes: {stats['changed']}, "
                     f"dzēsti: {stats['removed']}")
    lines.append("")
    cur = None
    for f in shown:
        if f.severity != cur:
            cur = f.severity
            lines.append((COLORS[cur] if color else "") + f"== {cur} ==" + (RESET if color else ""))
        loc = f"{f.path}:{f.line}" if f.line else f.path
        mark = " [JAUNS]" if f.new else ""
        lines.append(f"[{f.rule}]{mark} {f.title}")
        lines.append(f"    {loc.replace(str(HOME), '~')}")
        lines.append(f"    » {f.snippet}")
    if not shown:
        lines.append("Atradumu nav šajā smaguma līmenī. ✔")
    return "\n".join(lines)


def render_md(findings, stats):
    out = [f"# Claude privātuma audits — {stats['time']}", "",
           f"Skenēti faili: **{stats['files']}**", ""]
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        items = sorted((f for f in findings if f.severity == sev),
                       key=lambda f: (f.path, f.line))
        out.append(f"## {sev} ({len(items)})")
        for f in items:
            loc = (f"{f.path}:{f.line}" if f.line else f.path).replace(str(HOME), "~")
            out.append(f"- **[{f.rule}]**{' 🆕' if f.new else ''} {f.title}  \n  `{loc}`  \n  `{f.snippet.replace('`', chr(39))}`")
        out.append("")
    return "\n".join(out)


def notify(title, msg):
    if sys.platform != "darwin":
        return
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{esc(msg)}" with title "{esc(title)}" sound name "Basso"'],
                       check=False, timeout=10)
    except Exception:
        pass


# --------------------------------------------------------------- grafiks
def install_schedule(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    WORK.mkdir(parents=True, exist_ok=True)
    dst = WORK / "claude_privatuma_audits.py"
    if Path(__file__).resolve() != dst.resolve():
        shutil.copy2(__file__, dst)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(dst), "--quiet", "--notify"],
        "StartCalendarInterval": {"Hour": h, "Minute": m},
        "RunAtLoad": False,
        "StandardOutPath": str(WORK / "launchd.out.log"),
        "StandardErrorPath": str(WORK / "launchd.err.log"),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as fh:
        plistlib.dump(plist, fh)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)],
                       capture_output=True, text=True)
    if r.returncode:
        print("launchctl kļūda:", r.stderr.strip())
        return 1
    print(f"Ieplānots katru dienu plkst. {hhmm}. Skripts: {dst}\nPārskati: {REPORTS}")
    return 0


def uninstall_schedule():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("Plānotais uzdevums noņemts.")
    return 0


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Claude privātuma audits")
    ap.add_argument("--path", action="append", default=[], help="papildu fails/mape/.skill/.zip")
    ap.add_argument("--no-default", action="store_true", help="neskenēt standarta vietas")
    ap.add_argument("--min-severity", default="LOW", choices=list(SEV_ORDER))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="bez izvades termināļā")
    ap.add_argument("--no-save", action="store_true", help="nesaglabāt stāvokli/pārskatu")
    ap.add_argument("--install-schedule", action="store_true")
    ap.add_argument("--uninstall-schedule", action="store_true")
    ap.add_argument("--time", default="09:07", help="ikdienas palaišanas laiks HH:MM")
    a = ap.parse_args()

    if a.install_schedule:
        return install_schedule(a.time)
    if a.uninstall_schedule:
        return uninstall_schedule()

    cfg = load_config()
    targets = ([] if a.no_default else default_targets()) + \
              [Path(p).expanduser() for p in a.path + cfg["extra_paths"]]
    if not targets:
        print("Nav ko skenēt: nav atrasta neviena Claude mape. Izmanto --path.")
        return 0

    findings, hashes, nfiles = audit(targets, cfg)

    prev = load_json(STATE, {})
    known = set(prev.get("findings", []))
    old_hash = prev.get("hashes", {})
    first_run = not prev
    for f in findings:
        f.new = (not first_run) and f.fp() not in known
    changed = [p for p, h in hashes.items() if old_hash.get(p) != h] if not first_run else []
    removed = [p for p in old_hash if p not in hashes] if not first_run else []
    stats = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "files": nfiles,
             "changed": len(changed), "removed": len(removed)}

    if not a.no_save:
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        (REPORTS / f"{stamp}.md").write_text(render_md(findings, stats), encoding="utf-8")
        (REPORTS / "pedejais.json").write_text(
            json.dumps({"stats": stats, "findings": [asdict(f) for f in findings]},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        STATE.write_text(json.dumps({"findings": [f.fp() for f in findings],
                                     "hashes": hashes}), encoding="utf-8")
        for old in sorted(REPORTS.glob("20*.md"))[:-60]:
            old.unlink(missing_ok=True)

    if not a.quiet:
        if a.json:
            print(json.dumps({"stats": stats, "findings": [asdict(f) for f in findings]},
                             ensure_ascii=False, indent=2))
        else:
            print(render_text(findings, stats, a.min_severity, sys.stdout.isatty()))
            if not a.no_save:
                print(f"\nPilns pārskats: {REPORTS}/")

    serious = [f for f in findings if SEV_ORDER[f.severity] >= 3]
    new_serious = [f for f in serious if f.new or first_run]
    if a.notify and new_serious:
        top = new_serious[0]
        notify("Claude privātuma audits",
               f"{len(new_serious)} nopietni atradumi (HIGH/CRITICAL). Pirmais: {top.title}")
    if serious:
        return 2
    return 1 if any(f.severity == "MEDIUM" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
