# 🤖 Slack Attendance Bot — Linux Setup Guide

> **Für neue Linux-Nutzer** — Schritt für Schritt erklärt, mit allen Befehlen zum Kopieren.

---

## 📋 Inhaltsverzeichnis

1. [Was macht dieser Bot?](#1-was-macht-dieser-bot)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Schritt 1 — Repository klonen](#schritt-1--repository-klonen)
4. [Schritt 2 — Python & Abhängigkeiten installieren](#schritt-2--python--abhängigkeiten-installieren)
5. [Schritt 3 — Playwright Browser installieren](#schritt-3--playwright-browser-installieren)
6. [Schritt 4 — Konfiguration (.env Datei)](#schritt-4--konfiguration-env-datei)
7. [Schritt 5 — Ersten Start ausführen](#schritt-5--ersten-start-ausführen)
8. [Schritt 6 — Automatisch per Cron planen](#schritt-6--automatisch-per-cron-planen)
9. [Schritt 7 — Automatisch per Systemd planen (empfohlen)](#schritt-7--automatisch-per-systemd-planen-empfohlen)
10. [Troubleshooting — Häufige Fehler](#troubleshooting--häufige-fehler)

---

## 1. Was macht dieser Bot?

Der Slack Attendance Bot **loggt sich automatisch in Slack ein** und klickt für dich auf „Present" in einem Anwesenheits-Formular — jeden Tag, pünktlich, ohne dass du es vergisst.

```
Bot startet → Slack-Login → Kanal öffnen → "Present" klicken → Fertig ✅
```

---

## 2. Voraussetzungen

Überprüfe zuerst, ob folgendes auf deinem System vorhanden ist:

```bash
# Python-Version prüfen (mindestens 3.9 erforderlich)
python3 --version
```

Falls Python nicht installiert ist:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

Weitere benötigte Pakete:

```bash
sudo apt install git curl -y
```

> **Hinweis:** Diese Befehle funktionieren auf **Ubuntu/Debian**. Bei anderen Distributionen ersetze `apt` durch `dnf` (Fedora) oder `pacman` (Arch).

---

## Schritt 1 — Repository klonen

Lade den Bot-Code auf deinen Computer:

```bash
git clone https://github.com/jaywee92/Slack-Attendance-Bot.git
```

Wechsle in den neuen Ordner:

```bash
cd Slack-Attendance-Bot
```

Überprüfe, dass alle Dateien vorhanden sind:

```bash
ls -la
```

Du solltest diese Dateien sehen: `attendance_bot.py`, `requirements.txt`, `.env.example`, `docker-compose.yml`, `examples/`

---

## Schritt 2 — Python & Abhängigkeiten installieren

### 2a — Virtuelle Umgebung erstellen (empfohlen)

Eine virtuelle Umgebung hält die Bot-Pakete getrennt vom Rest deines Systems:

```bash
python3 -m venv venv
```

Virtuelle Umgebung aktivieren:

```bash
source venv/bin/activate
```

> ✅ Du siehst nun `(venv)` am Anfang deiner Kommandozeile — das ist korrekt.

### 2b — Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

Erfolgreiche Ausgabe sieht ungefähr so aus:

```
Successfully installed playwright-1.58.0 python-dotenv-1.0.0 ...
```

---

## Schritt 3 — Playwright Browser installieren

Playwright braucht einen echten Browser (Chromium), um Slack zu steuern:

```bash
python -m playwright install
```

Das dauert 1–2 Minuten und lädt ca. 200 MB herunter.

Nur Chromium installieren (spart Speicherplatz):

```bash
python -m playwright install chromium
```

Systemabhängigkeiten installieren (wichtig auf Server ohne Desktop!):

```bash
python -m playwright install-deps chromium
```

Überprüfen ob alles funktioniert:

```bash
python -m playwright --version
```

---

## Schritt 4 — Konfiguration (.env Datei)

### 4a — .env Datei erstellen

Kopiere die Vorlage:

```bash
cp .env.example .env
```

Öffne die Datei mit einem Texteditor:

```bash
nano .env
```

> **Alternativer Editor:** `vim .env` oder `gedit .env` (Desktop)

### 4b — Pflichtfelder ausfüllen

Ersetze die Platzhalter mit deinen echten Daten:

```env
# ── Pflichtfelder ──────────────────────────────────────
SLACK_EMAIL=deine@email.de
SLACK_PASSWORD=deinPasswort123

# Deine Slack Workspace-Adresse (ohne https://)
WORKSPACE_DOMAIN=deinworkspace.slack.com

# Nur der Name des Workspaces (ohne .slack.com)
WORKSPACE_SLUG=deinworkspace
```

### 4c — Optionale Einstellungen (für Fortgeschrittene)

```env
# ── Optionale Felder ───────────────────────────────────
# Headless = true → Browser unsichtbar im Hintergrund
HEADLESS=true

# Bei erstem Login: true setzen (für Sicherheits-Code Eingabe)
ALLOW_INTERACTIVE_LOGIN=false

# Log-Level: INFO (normal) oder DEBUG (ausführlich)
LOG_LEVEL=INFO

# Log in Datei speichern
LOG_FILE=/home/deinuser/slack-bot/bot.log

# Timeout für das Suchen des "Present"-Buttons (Sekunden)
FIND_PRESENT_TIMEOUT_S=45
```

### 4d — Datei speichern

In `nano`: Drücke `Ctrl + O`, dann `Enter`, dann `Ctrl + X`

### ⚠️ Sicherheitshinweis

Die `.env` Datei enthält dein Passwort — **niemals** in Git hochladen!

```bash
# Überprüfen ob .env im .gitignore steht
cat .gitignore | grep .env
```

Du solltest `.env` in der Ausgabe sehen ✅

---

## Schritt 5 — Ersten Start ausführen

### 5a — Virtuelle Umgebung aktivieren (falls noch nicht aktiv)

```bash
cd ~/Slack-Attendance-Bot
source venv/bin/activate
```

### 5b — Bot starten

```bash
python attendance_bot.py
```

### 5c — Ausgabe verstehen

| Ausgabe | Bedeutung |
|--------|-----------|
| `STATE=RUN_STARTED` | Bot startet |
| `STATE=SESSION_INVALID` | Kein Login gespeichert — erster Start |
| `STATE=LOGIN_REQUIRED` | Bot loggt sich jetzt ein |
| `STATE=LOGIN_AUTHENTICATED` | Login erfolgreich ✅ |
| `STATE=PRESENT_RECORDED` | "Present" geklickt — fertig! ✅ |
| `STATE=SURVEY_CLOSED` | Formular bereits geschlossen |
| `STATE=RUN_FAILED` | Fehler aufgetreten ❌ |

### 5d — Erster Login mit Sicherheits-Code

Beim allerersten Start schickt Slack einen **Sicherheits-Code** per E-Mail. Damit der Bot diesen Code eingeben kann, setze vorübergehend:

```bash
# In .env Datei ändern:
ALLOW_INTERACTIVE_LOGIN=true
```

Dann Bot starten:

```bash
python attendance_bot.py
```

Der Bot pausiert und fragt:

```
Enter security code from email:
```

Gib den Code aus deiner E-Mail ein und drücke `Enter`. Nach erfolgreichem Login:

```bash
# Wieder auf false setzen (für automatischen Betrieb)
# Öffne .env und setze:
ALLOW_INTERACTIVE_LOGIN=false
```

Die Login-Session wird in `slack_auth.json` gespeichert. Beim nächsten Start ist kein Code mehr nötig.

---

## Schritt 6 — Automatisch per Cron planen

Cron ist der einfachste Weg, den Bot automatisch täglich auszuführen.

### 6a — Pfade herausfinden

```bash
# Absoluten Pfad von Python im venv
which python3
# Beispielausgabe: /home/jaywee92/Slack-Attendance-Bot/venv/bin/python3

# Absoluten Pfad des Bot-Skripts
realpath attendance_bot.py
# Beispielausgabe: /home/jaywee92/Slack-Attendance-Bot/attendance_bot.py
```

### 6b — Crontab öffnen

```bash
crontab -e
```

Falls gefragt wird, welchen Editor: Wähle `1` für `nano`

### 6c — Automatischen Job hinzufügen

Füge am Ende der Datei diese Zeile ein:

```cron
# Slack Attendance Bot — täglich 9:05 Uhr und 14:05 Uhr (Mo-Fr)
5 9,14 * * 1-5 cd /home/DEIN_USERNAME/Slack-Attendance-Bot && /home/DEIN_USERNAME/Slack-Attendance-Bot/venv/bin/python3 attendance_bot.py >> /home/DEIN_USERNAME/slack-bot.log 2>&1
```

> 🔁 Ersetze `DEIN_USERNAME` durch deinen tatsächlichen Linux-Benutzernamen!

Deinen Benutzernamen findest du mit:

```bash
whoami
```

### 6d — Crontab speichern und prüfen

In nano: `Ctrl + O` → `Enter` → `Ctrl + X`

Crontab-Inhalt anzeigen:

```bash
crontab -l
```

### 6e — Log anschauen

Nach dem nächsten geplanten Lauf:

```bash
tail -f ~/slack-bot.log
```

---

## Schritt 7 — Automatisch per Systemd planen (empfohlen)

Systemd ist zuverlässiger als Cron und funktioniert auch nach einem Server-Neustart korrekt.

### 7a — Systemd User-Verzeichnis erstellen

```bash
mkdir -p ~/.config/systemd/user/
```

### 7b — Service-Datei anpassen und kopieren

Öffne die Beispiel-Service-Datei:

```bash
cat examples/slack-attendance-bot.service
```

Kopiere sie in dein Systemd-Verzeichnis:

```bash
cp examples/slack-attendance-bot.service ~/.config/systemd/user/
```

Öffne und passe die Pfade an:

```bash
nano ~/.config/systemd/user/slack-attendance-bot.service
```

Ersetze die Pfade durch deine echten Pfade:

```ini
[Unit]
Description=Slack Attendance Bot
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/DEIN_USERNAME/Slack-Attendance-Bot
ExecStart=/home/DEIN_USERNAME/Slack-Attendance-Bot/venv/bin/python3 /home/DEIN_USERNAME/Slack-Attendance-Bot/attendance_bot.py
EnvironmentFile=/home/DEIN_USERNAME/Slack-Attendance-Bot/.env
StandardOutput=append:/home/DEIN_USERNAME/slack-bot.log
StandardError=append:/home/DEIN_USERNAME/slack-bot.log

[Install]
WantedBy=default.target
```

### 7c — Timer-Datei anpassen und kopieren

```bash
cp examples/slack-attendance-bot.timer ~/.config/systemd/user/
nano ~/.config/systemd/user/slack-attendance-bot.timer
```

Inhalt der Timer-Datei:

```ini
[Unit]
Description=Slack Attendance Bot Timer (09:05 und 14:05, Mo-Fr)

[Timer]
OnCalendar=Mon-Fri 09:05
OnCalendar=Mon-Fri 14:05
Persistent=true

[Install]
WantedBy=timers.target
```

### 7d — Systemd neu laden und Timer aktivieren

```bash
# Systemd neu laden
systemctl --user daemon-reload

# Timer aktivieren und sofort starten
systemctl --user enable --now slack-attendance-bot.timer

# Status prüfen
systemctl --user status slack-attendance-bot.timer
```

### 7e — Nächsten geplanten Lauf anzeigen

```bash
systemctl --user list-timers --all | grep slack
```

### 7f — Bot manuell testen (ohne auf Cron/Timer warten)

```bash
systemctl --user start slack-attendance-bot.service

# Log live anschauen
journalctl --user -u slack-attendance-bot.service -f
```

---

## Troubleshooting — Häufige Fehler

### ❌ `ModuleNotFoundError: No module named 'playwright'`

Virtuelle Umgebung nicht aktiviert:

```bash
source ~/Slack-Attendance-Bot/venv/bin/activate
pip install -r requirements.txt
```

---

### ❌ `Executable doesn't exist` oder Browser-Fehler

Playwright-Browser fehlen:

```bash
source ~/Slack-Attendance-Bot/venv/bin/activate
python -m playwright install chromium
python -m playwright install-deps chromium
```

---

### ❌ `STATE=SESSION_INVALID` — Bot loggt sich nicht ein

Session ist abgelaufen. Neuen Login durchführen:

```bash
# In .env setzen:
ALLOW_INTERACTIVE_LOGIN=true

# Dann starten und Sicherheits-Code eingeben
python attendance_bot.py

# Danach wieder zurücksetzen:
ALLOW_INTERACTIVE_LOGIN=false
```

---

### ❌ `STATE=RUN_FAILED` — Allgemeiner Fehler

Detailliertes Logging aktivieren:

```bash
# In .env setzen:
LOG_LEVEL=DEBUG
HEADLESS=false

# Bot starten und Browser-Fenster beobachten
python attendance_bot.py
```

---

### ❌ `Permission denied` beim Cron

Bot-Skript ausführbar machen:

```bash
chmod +x ~/Slack-Attendance-Bot/attendance_bot.py
```

---

### ❌ Bot läuft, aber kein "Present" gefunden

Mögliche Ursachen:
- Das Formular wurde noch nicht geöffnet
- `FIND_PRESENT_TIMEOUT_S` zu niedrig gesetzt

Timeout erhöhen in `.env`:

```env
FIND_PRESENT_TIMEOUT_S=90
```

---

### 📋 Log-Datei live anschauen

```bash
# Bei Cron
tail -f ~/slack-bot.log

# Bei Systemd
journalctl --user -u slack-attendance-bot.service -n 50 --no-pager
```

---

### 🔄 Bot-Status nach jedem Lauf prüfen

| Exit Code | Bedeutung |
|-----------|-----------|
| `0` | Erfolgreich — "Present" geklickt ✅ |
| `2` | Keine gültige Session — Login erforderlich |
| `3` | "Present" nicht gefunden — Formular möglicherweise geschlossen |

Letzten Exit-Code prüfen:

```bash
python attendance_bot.py; echo "Exit Code: $?"
```

---

## ✅ Zusammenfassung — Alle Befehle auf einen Blick

```bash
# 1. Repository klonen
git clone https://github.com/jaywee92/Slack-Attendance-Bot.git
cd Slack-Attendance-Bot

# 2. Virtuelle Umgebung erstellen und aktivieren
python3 -m venv venv
source venv/bin/activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium

# 4. Konfiguration erstellen
cp .env.example .env
nano .env          # Deine Zugangsdaten eintragen

# 5. Bot testen
python attendance_bot.py

# 6a. Cron einrichten (einfach)
crontab -e
# Zeile einfügen: 5 9,14 * * 1-5 cd ~/Slack-Attendance-Bot && ./venv/bin/python3 attendance_bot.py

# 6b. ODER Systemd einrichten (empfohlen)
cp examples/slack-attendance-bot.service ~/.config/systemd/user/
cp examples/slack-attendance-bot.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now slack-attendance-bot.timer
```

---

## 📞 Hilfe & Support

- **GitHub Issues:** [github.com/jaywee92/Slack-Attendance-Bot/issues](https://github.com/jaywee92/Slack-Attendance-Bot/issues)
- **Vollständige Dokumentation:** [README.md](README.md)

---

*Guide erstellt für neue Linux-Nutzer · Getestet auf Ubuntu 22.04 LTS*
