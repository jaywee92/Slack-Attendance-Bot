# Slack Attendance Bot

A small Playwright-based bot that logs into Slack and marks the latest attendance form as **Present** in a specific channel. It stores an authenticated session locally so subsequent runs are headless and fast.

## Features
- Logs in once, then reuses the saved session (`slack_auth.json`)
- Validates the session before each run and re-authenticates if needed
- Marks the newest "Present" radio option in the target channel
- Designed to run as a single execution (schedule externally)

## Requirements
- Python 3.9+
- Playwright
- python-dotenv

## Setup
1. Install dependencies:
```bash
python -m pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
python -m playwright install
```

3. Create a `.env` file:
```bash
cp .env.example .env
```

4. Edit `.env` and set your Slack credentials:
```
SLACK_EMAIL=you@example.com
SLACK_PASSWORD=your_password
```

5. Update the Slack IDs in `attendance_bot.py` if needed:
- `TEAM_ID`
- `CHANNEL_ID`

## Run
```bash
python attendance_bot.py
```

## How It Works
Note: All Playwright browsers are currently started with `headless=False`. After the first successful run, change all `headless` flags to `True` for fully headless execution.

- On the first run, a visible browser window opens so you can log in.
- A session is saved to `slack_auth.json`.
- Subsequent runs use the stored session in headless mode.
- If the session is invalid or expired, the bot re-authenticates.

## Scheduling
Because the script is single-run, schedule it externally. Example configs are in `examples/`.

### Linux (cron)
- Use `crontab -e` and paste the contents of `examples/cron.txt`.
- Update the Python path and project path to match your environment.

### Linux (systemd user timer)
1. Copy `examples/slack-attendance-bot.service` and `examples/slack-attendance-bot.timer` to `~/.config/systemd/user/`.
2. Update paths inside both files.
3. Run:
```bash
systemctl --user daemon-reload
systemctl --user enable --now slack-attendance-bot.timer
```

### macOS (launchd)
1. Copy `examples/com.jaywee.slack-attendance-bot.plist` to `~/Library/LaunchAgents/`.
2. Update paths inside the plist.
3. Load it:
```bash
launchctl load -w ~/Library/LaunchAgents/com.jaywee.slack-attendance-bot.plist
```

## Security Notes
- Do **not** commit `.env` or `slack_auth.json`.
- Both are excluded via `.gitignore`.

## Troubleshooting
- If no "Present" button is found, check that the attendance form is visible in the channel.
- If login fails, verify credentials in `.env`.
- If the session expires, delete `slack_auth.json` to force a new login.
