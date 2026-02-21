# 🤖 Slack Attendance Bot — Linux Setup Guide

> **For new Linux users** — A clear, step-by-step guide with every command ready to copy and paste.

---

## 📋 Table of Contents

1. [What does this bot do?](#1-what-does-this-bot-do)
2. [Requirements](#2-requirements)
3. [Step 1 — Clone the Repository](#step-1--clone-the-repository)
4. [Step 2 — Install Python & Dependencies](#step-2--install-python--dependencies)
5. [Step 3 — Install the Playwright Browser](#step-3--install-the-playwright-browser)
6. [Step 4 — Configuration (.env file)](#step-4--configuration-env-file)
7. [Step 5 — Run the Bot for the First Time](#step-5--run-the-bot-for-the-first-time)
8. [Step 6 — Schedule Automatically with Cron](#step-6--schedule-automatically-with-cron)
9. [Step 7 — Schedule Automatically with Systemd (Recommended)](#step-7--schedule-automatically-with-systemd-recommended)
10. [Step 8 — Run with Docker (Optional)](#step-8--run-with-docker-optional)
11. [Troubleshooting — Common Errors](#troubleshooting--common-errors)

---

## 1. What does this bot do?

The Slack Attendance Bot **automatically logs into Slack and clicks "Present"** on an attendance form — every day, on time, so you never forget.

```
Bot starts → Slack login → Open channel → Click "Present" → Done ✅
```

Once set up, the bot runs completely in the background on a schedule you define. No manual action required.

---

## 2. Requirements

Before you begin, check that the following are available on your system:

```bash
# Check Python version — at least 3.9 is required
python3 --version
```

If Python is not installed:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

Also install Git and Curl:

```bash
sudo apt install git curl -y
```

> **Note:** These commands work on **Ubuntu / Debian**. On other distributions, replace `apt` with `dnf` (Fedora) or `pacman` (Arch Linux).

---

## Step 1 — Clone the Repository

Download the bot's code to your computer:

```bash
git clone https://github.com/jaywee92/Slack-Attendance-Bot.git
```

Move into the new folder:

```bash
cd Slack-Attendance-Bot
```

Verify that all files are present:

```bash
ls -la
```

You should see these files: `attendance_bot.py`, `requirements.txt`, `.env.example`, `docker-compose.yml`, `examples/`

---

## Step 2 — Install Python & Dependencies

### 2a — Create a Virtual Environment (Recommended)

A virtual environment keeps the bot's packages separate from the rest of your system — this avoids conflicts with other Python projects:

```bash
python3 -m venv venv
```

Activate the virtual environment:

```bash
source venv/bin/activate
```

> ✅ You will now see `(venv)` at the beginning of your command prompt — that is correct and expected.

### 2b — Install Dependencies

```bash
pip install -r requirements.txt
```

A successful installation looks like this:

```
Successfully installed playwright-1.58.0 python-dotenv-1.0.0 ...
```

---

## Step 3 — Install the Playwright Browser

Playwright controls a real browser (Chromium) to interact with Slack. It needs to be downloaded separately:

```bash
python -m playwright install chromium
```

This takes 1–2 minutes and downloads approximately 200 MB.

Install the required system-level browser dependencies (important on servers without a desktop environment!):

```bash
python -m playwright install-deps chromium
```

Verify the installation worked:

```bash
python -m playwright --version
```

---

## Step 4 — Configuration (.env file)

### 4a — Create the .env File

Copy the provided template:

```bash
cp .env.example .env
```

Open the file in a text editor:

```bash
nano .env
```

> **Alternative editors:** `vim .env` or `gedit .env` (if you have a desktop)

### 4b — Fill in the Required Fields

Replace the placeholder values with your actual credentials:

```env
# ── Required fields ────────────────────────────────────
SLACK_EMAIL=your@email.com
SLACK_PASSWORD=yourPassword123

# Your Slack workspace address (without https://)
WORKSPACE_DOMAIN=yourworkspace.slack.com

# Only the workspace name (without .slack.com)
WORKSPACE_SLUG=yourworkspace
```

### 4c — Optional Settings (for Advanced Users)

```env
# ── Optional fields ────────────────────────────────────
# Headless = true → browser runs invisibly in the background
HEADLESS=true

# Set to true only for the very first login (to enter your security code)
ALLOW_INTERACTIVE_LOGIN=false

# Log level: INFO (normal) or DEBUG (very detailed output)
LOG_LEVEL=INFO

# Save log output to a file
LOG_FILE=/home/yourusername/slack-bot/bot.log

# Timeout for finding the "Present" button (in seconds)
FIND_PRESENT_TIMEOUT_S=45
```

### 4d — Save the File

In `nano`: Press `Ctrl + O`, then `Enter`, then `Ctrl + X` to save and exit.

### ⚠️ Security Warning

The `.env` file contains your Slack password — **never** commit it to Git or share it publicly.

Check that `.env` is listed in `.gitignore`:

```bash
cat .gitignore | grep .env
```

You should see `.env` in the output ✅

---

## Step 5 — Run the Bot for the First Time

### 5a — Activate the Virtual Environment (if not already active)

```bash
cd ~/Slack-Attendance-Bot
source venv/bin/activate
```

### 5b — Start the Bot

```bash
python attendance_bot.py
```

### 5c — Understanding the Output

The bot logs its progress using `STATE=` markers:

| Output | Meaning |
|--------|---------|
| `STATE=RUN_STARTED` | Bot is starting up |
| `STATE=SESSION_INVALID` | No saved login found — first run |
| `STATE=LOGIN_REQUIRED` | Bot is now logging into Slack |
| `STATE=LOGIN_AUTHENTICATED` | Login successful ✅ |
| `STATE=PRESENT_RECORDED` | "Present" was clicked — done! ✅ |
| `STATE=SURVEY_CLOSED` | Attendance form is already closed |
| `STATE=RUN_FAILED` | Something went wrong ❌ |

### 5d — First Login: Entering a Security Code

On the very first run, Slack will send a **security code to your email**. To allow the bot to enter this code interactively, temporarily set:

```bash
# Open your .env file and change:
ALLOW_INTERACTIVE_LOGIN=true
```

Then start the bot:

```bash
python attendance_bot.py
```

The bot will pause and prompt you:

```
Enter security code from email:
```

Type the code from your email and press `Enter`. After a successful login:

```bash
# Open .env again and set it back to false (for automated use):
ALLOW_INTERACTIVE_LOGIN=false
```

The login session is saved to `slack_auth.json`. Future runs will not require a code unless the session expires.

---

## Step 6 — Schedule Automatically with Cron

Cron is the simplest way to run the bot automatically at set times every day.

### 6a — Find Your Paths

```bash
# Full path to Python inside the virtual environment
which python3
# Example output: /home/jaywee92/Slack-Attendance-Bot/venv/bin/python3

# Full path to the bot script
realpath attendance_bot.py
# Example output: /home/jaywee92/Slack-Attendance-Bot/attendance_bot.py
```

### 6b — Open the Crontab Editor

```bash
crontab -e
```

If asked which editor to use, type `1` and press Enter to select `nano`.

### 6c — Add the Scheduled Job

Add this line at the very end of the file:

```cron
# Slack Attendance Bot — runs at 09:05 and 14:05, Monday to Friday
5 9,14 * * 1-5 cd /home/YOUR_USERNAME/Slack-Attendance-Bot && /home/YOUR_USERNAME/Slack-Attendance-Bot/venv/bin/python3 attendance_bot.py >> /home/YOUR_USERNAME/slack-bot.log 2>&1
```

> 🔁 Replace `YOUR_USERNAME` with your actual Linux username!

To find your username, run:

```bash
whoami
```

### 6d — Save and Verify

In nano: `Ctrl + O` → `Enter` → `Ctrl + X`

Check that the job was saved:

```bash
crontab -l
```

### 6e — Watch the Log

After the next scheduled run:

```bash
tail -f ~/slack-bot.log
```

Press `Ctrl + C` to stop following the log.

---

## Step 7 — Schedule Automatically with Systemd (Recommended)

Systemd timers are more reliable than Cron. They survive server reboots, retry after missed runs, and integrate with the system journal.

### 7a — Create the Systemd User Directory

```bash
mkdir -p ~/.config/systemd/user/
```

### 7b — Copy and Edit the Service File

Copy the example service file:

```bash
cp examples/slack-attendance-bot.service ~/.config/systemd/user/
```

Open it for editing:

```bash
nano ~/.config/systemd/user/slack-attendance-bot.service
```

Update all paths to match your system — replace `YOUR_USERNAME` with your real username:

```ini
[Unit]
Description=Slack Attendance Bot
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/YOUR_USERNAME/Slack-Attendance-Bot
ExecStart=/home/YOUR_USERNAME/Slack-Attendance-Bot/venv/bin/python3 /home/YOUR_USERNAME/Slack-Attendance-Bot/attendance_bot.py
EnvironmentFile=/home/YOUR_USERNAME/Slack-Attendance-Bot/.env
StandardOutput=append:/home/YOUR_USERNAME/slack-bot.log
StandardError=append:/home/YOUR_USERNAME/slack-bot.log

[Install]
WantedBy=default.target
```

Save: `Ctrl + O` → `Enter` → `Ctrl + X`

### 7c — Copy and Edit the Timer File

```bash
cp examples/slack-attendance-bot.timer ~/.config/systemd/user/
nano ~/.config/systemd/user/slack-attendance-bot.timer
```

The timer file should look like this:

```ini
[Unit]
Description=Slack Attendance Bot Timer (09:05 and 14:05, Mon–Fri)

[Timer]
OnCalendar=Mon-Fri 09:05
OnCalendar=Mon-Fri 14:05
Persistent=true

[Install]
WantedBy=timers.target
```

Save and exit.

### 7d — Enable and Start the Timer

```bash
# Reload systemd to pick up the new files
systemctl --user daemon-reload

# Enable the timer so it starts automatically on login/boot
systemctl --user enable --now slack-attendance-bot.timer

# Check the timer status
systemctl --user status slack-attendance-bot.timer
```

### 7e — View the Next Scheduled Run

```bash
systemctl --user list-timers --all | grep slack
```

### 7f — Test the Bot Manually (Without Waiting for the Timer)

```bash
systemctl --user start slack-attendance-bot.service
```

View the live log output:

```bash
journalctl --user -u slack-attendance-bot.service -f
```

Press `Ctrl + C` to stop.

---

## Step 8 — Run with Docker (Optional)

Docker is an alternative to the manual Python setup. It packages the bot and all its dependencies (including the Chromium browser) into an isolated container — no virtual environment, no `playwright install` needed.

> **When to use Docker?**
> - You manage multiple projects and want clean isolation
> - You are running the bot on a server without a desktop environment
> - You are familiar with Docker and prefer container-based workflows

---

### 8a — Install Docker

If Docker is not yet installed:

```bash
# Install Docker Engine (Ubuntu/Debian)
sudo apt update
sudo apt install -y ca-certificates curl gnupg
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group (so you don't need sudo every time)
sudo usermod -aG docker $USER

# Log out and back in for the group change to take effect
# Then verify the installation:
docker --version
docker compose version
```

---

### 8b — Clone the Repository

```bash
git clone https://github.com/jaywee92/Slack-Attendance-Bot.git
cd Slack-Attendance-Bot
```

---

### 8c — Create the .env File

```bash
cp .env.example .env
nano .env
```

Fill in your credentials exactly as described in [Step 4](#step-4--configuration-env-file).

> **Important for Docker:** Set `HEADLESS=true` — the container has no display.

---

### 8d — Build and Run the Container

Build the Docker image (only needs to be done once, or after code changes):

```bash
docker compose build
```

Run the bot once:

```bash
docker compose run --rm bot
```

The `--rm` flag removes the temporary container after it finishes — the saved login session is stored in a persistent Docker volume (`session_data`) and survives between runs.

---

### 8e — First Login Inside Docker

On the very first run, Slack will send a security code to your email. To allow interactive input:

```bash
# In .env, temporarily set:
ALLOW_INTERACTIVE_LOGIN=true
```

Then run:

```bash
docker compose run --rm -it bot
```

Enter the security code when prompted. After successful login, restore the setting:

```bash
# In .env, set it back:
ALLOW_INTERACTIVE_LOGIN=false
```

The session is saved inside the `session_data` volume and will be reused on future runs.

---

### 8f — Schedule with Cron (Docker)

Instead of activating a virtual environment, use `docker compose run` inside your cron job:

```bash
crontab -e
```

Add this line (replace `/home/YOUR_USERNAME` with your actual path):

```cron
# Slack Attendance Bot via Docker — runs at 09:05 and 14:05, Monday to Friday
5 9,14 * * 1-5 cd /home/YOUR_USERNAME/Slack-Attendance-Bot && docker compose run --rm bot >> /home/YOUR_USERNAME/slack-bot-docker.log 2>&1
```

---

### 8g — Debug Mode with VNC (View the Browser Remotely)

The repository includes a special `bot-vnc` Docker service that starts a visible browser session you can watch remotely via a web browser — useful for debugging.

**Start the VNC container:**

```bash
# First, change the default VNC password in docker-compose.yml:
# Look for: VNC_PASSWORD=change-me
nano docker-compose.yml

# Then start the VNC service:
docker compose --profile debug up bot-vnc
```

**Open a browser and navigate to:**

```
http://YOUR_SERVER_IP:6080
```

You will see a live view of the browser controlled by the bot. Press `Ctrl + C` in the terminal to stop the container.

> 🔒 **Security:** Never expose port `6080` or `5900` to the public internet without a firewall rule or VPN. Use these ports only on a local network or over SSH tunnelling.

---

### 8h — Useful Docker Commands

```bash
# View the saved login session volume
docker volume inspect slack-attendance-bot_session_data

# Remove the saved session (forces fresh login on next run)
docker volume rm slack-attendance-bot_session_data

# View logs from the last run
docker compose logs bot

# Remove all stopped containers (cleanup)
docker compose down
```

---

## Troubleshooting — Common Errors

### ❌ `ModuleNotFoundError: No module named 'playwright'`

The virtual environment is not activated:

```bash
source ~/Slack-Attendance-Bot/venv/bin/activate
pip install -r requirements.txt
```

---

### ❌ `Executable doesn't exist` or browser-related error

The Playwright browser was not installed:

```bash
source ~/Slack-Attendance-Bot/venv/bin/activate
python -m playwright install chromium
python -m playwright install-deps chromium
```

---

### ❌ `STATE=SESSION_INVALID` — Bot does not log in

The saved session has expired. Perform a fresh login:

```bash
# In .env, set:
ALLOW_INTERACTIVE_LOGIN=true

# Start the bot and enter the security code when prompted
python attendance_bot.py

# Then reset in .env:
ALLOW_INTERACTIVE_LOGIN=false
```

---

### ❌ `STATE=RUN_FAILED` — General failure

Enable verbose logging to get more detail:

```bash
# In .env, set:
LOG_LEVEL=DEBUG
HEADLESS=false

# Start the bot and watch the browser window
python attendance_bot.py
```

---

### ❌ `Permission denied` in Cron

Make the script executable:

```bash
chmod +x ~/Slack-Attendance-Bot/attendance_bot.py
```

---

### ❌ Bot runs but "Present" button is not found

Possible causes:
- The attendance form has not been opened yet
- The `FIND_PRESENT_TIMEOUT_S` value is too low

Increase the timeout in `.env`:

```env
FIND_PRESENT_TIMEOUT_S=90
```

---

### 📋 View Log Output at Any Time

```bash
# If using Cron
tail -f ~/slack-bot.log

# If using Systemd
journalctl --user -u slack-attendance-bot.service -n 50 --no-pager
```

---

### 🔄 Exit Codes — What Do They Mean?

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success — "Present" was recorded ✅ |
| `2` | No valid session — login required |
| `3` | "Present" button not found — form may be closed |

Check the exit code manually:

```bash
python attendance_bot.py; echo "Exit code: $?"
```

---

## ✅ Quick Reference — All Commands at a Glance

### Option A — Native Python Setup

```bash
# 1. Clone the repository
git clone https://github.com/jaywee92/Slack-Attendance-Bot.git
cd Slack-Attendance-Bot

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium

# 4. Create and fill in the configuration file
cp .env.example .env
nano .env

# 5. Run the bot to test it
python attendance_bot.py

# 6a. Schedule with Cron (simple)
crontab -e
# Add: 5 9,14 * * 1-5 cd ~/Slack-Attendance-Bot && ./venv/bin/python3 attendance_bot.py

# 6b. OR schedule with Systemd (recommended)
cp examples/slack-attendance-bot.service ~/.config/systemd/user/
cp examples/slack-attendance-bot.timer   ~/.config/systemd/user/
# Edit both files and replace YOUR_USERNAME with your actual username
systemctl --user daemon-reload
systemctl --user enable --now slack-attendance-bot.timer
```

### Option B — Docker Setup

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # log out and back in after this

# 2. Clone the repository
git clone https://github.com/jaywee92/Slack-Attendance-Bot.git
cd Slack-Attendance-Bot

# 3. Configure
cp .env.example .env
nano .env   # set HEADLESS=true for Docker

# 4. Build the image
docker compose build

# 5. Run once to test
docker compose run --rm bot

# 6. Schedule with Cron (Docker)
crontab -e
# Add: 5 9,14 * * 1-5 cd ~/Slack-Attendance-Bot && docker compose run --rm bot
```

---

## 📞 Help & Support

- **GitHub Issues:** [github.com/jaywee92/Slack-Attendance-Bot/issues](https://github.com/jaywee92/Slack-Attendance-Bot/issues)
- **Full Documentation:** [README.md](README.md)

---

*Guide written for new Linux users · Tested on Ubuntu 22.04 LTS*
