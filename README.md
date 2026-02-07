# Slack Attendance Bot

A small Playwright-based bot that logs into Slack and marks the latest attendance form as **Present** in a specific channel. It stores an authenticated session locally so subsequent runs are headless and fast.

## Features
- Logs in once, then reuses the saved session (`slack_auth.json`)
- Validates the session before each run and re-authenticates if needed
- Marks the newest "Present" radio option in the target channel
- Designed to run as a single execution (schedule externally with cron/systemd)

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
- On the first run, a visible browser window opens so you can log in.
- A session is saved to `slack_auth.json`.
- Subsequent runs use the stored session in headless mode.
- If the session is invalid or expired, the bot re-authenticates.

## Scheduling (example: cron)
Because the script is single-run, schedule it externally:
```bash
# Every weekday at 09:05 and 14:05
5 9,14 * * 1-5 /usr/bin/python /path/to/attendance_bot.py
```

## Security Notes
- Do **not** commit `.env` or `slack_auth.json`.
- Both are excluded via `.gitignore`.

## Troubleshooting
- If no "Present" button is found, check that the attendance form is visible in the channel.
- If login fails, verify credentials in `.env`.
- If the session expires, delete `slack_auth.json` to force a new login.
