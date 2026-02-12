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
SESSION_FILE=slack_auth.json
HEADLESS=false
ALLOW_INTERACTIVE_LOGIN=false
LOG_LEVEL=INFO
LOG_FILE=
```

5. Update the Slack IDs in `attendance_bot.py` if needed:
- `TEAM_ID`
- `CHANNEL_ID`

## Run
```bash
python attendance_bot.py
```

## How It Works
Note: The script reads `HEADLESS`, `ALLOW_INTERACTIVE_LOGIN`, `LOG_LEVEL`, and `LOG_FILE` from `.env`.

- `HEADLESS` controls whether Chromium runs with or without UI.
- `ALLOW_INTERACTIVE_LOGIN=true` allows one-time login bootstrap when session is invalid.
- A session is saved to `slack_auth.json`.
- Subsequent runs use the stored session.
- If `ALLOW_INTERACTIVE_LOGIN=false` and session is invalid, the bot exits instead of trying login.

## Bot State Logging
The bot logs structured state lines in this format:
`STATE=<STATE_NAME> | <DETAIL>`

Important states:
- `RUN_STARTED`
- `SESSION_VALID`
- `LOGIN_REQUIRED`
- `SECURITY_CODE_REQUIRED`
- `SESSION_SAVED`
- `ATTENDANCE_ATTEMPT_STARTED`
- `PRESENT_RECORDED`
- `SURVEY_CLOSED`
- `RUN_COMPLETED`
- `RUN_FAILED`

Closed survey is detected from Slack messages like:
- `The survey is now closed. Further changes to your selections will not be recorded...`
- `The survey is closed! If you missed it due to an absence and want to submit a sick note, please click the button.`

Logging options:
- `LOG_LEVEL=INFO` (or `DEBUG`)
- `LOG_FILE=/session/attendance_bot.log` to write logs to a file in addition to stdout

## VPS / Docker Bootstrap (Secure Code)
Use this flow on terminal-only hosts when Slack requires a one-time security code:
1. Set `ALLOW_INTERACTIVE_LOGIN=true` in `.env`.
2. Run the container interactively (`-it`) once so `input()` can prompt for the code.
3. Enter the security code in the terminal prompt.
4. Verify that `slack_auth.json` was created in your mounted persistent volume.
5. Set `ALLOW_INTERACTIVE_LOGIN=false` for normal scheduled runs.

Example bootstrap run:
```bash
docker run --rm -it \\
  -v /opt/slack-attendance/session:/session \\
  --env-file .env \\
  -e SESSION_FILE=/session/slack_auth.json \\
  your-image python attendance_bot.py
```

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


### Windows (Task Scheduler)
1. Open **Task Scheduler** and choose **Create Task**.
2. **General**: give it a name (e.g., Slack Attendance Bot).
3. **Triggers**: create two triggers at 09:05 and 14:05 (or your desired times).
4. **Actions**: Start a program.
   - **Program/script**: the full path to `python.exe` (e.g., `C:\Users\you\AppData\Local\Programs\Python\Python311\python.exe`)
   - **Add arguments**: the full path to `attendance_bot.py`
   - **Start in**: the project folder (so `.env` is found)
5. Save the task.

Optional CLI example:
```bat
schtasks /Create /TN "Slack Attendance Bot AM" /TR "C:\Path\To\python.exe C:\Path\To\attendance_bot.py" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:05
schtasks /Create /TN "Slack Attendance Bot PM" /TR "C:\Path\To\python.exe C:\Path\To\attendance_bot.py" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 14:05
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
