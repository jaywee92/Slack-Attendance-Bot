from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import time
import os
import logging

# Slack workspace and channel identifiers
TEAM_ID = "TNS9HAY6M"
CHANNEL_ID = "C09BXD87H54"

# Load credentials from .env file
load_dotenv()
EMAIL = os.getenv("SLACK_EMAIL")
PASSWORD = os.getenv("SLACK_PASSWORD")
SESSION_FILE = os.getenv("SESSION_FILE", "slack_auth.json")
LOG_FILE = os.getenv("LOG_FILE")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logger():
    handlers = [logging.StreamHandler()]
    if LOG_FILE:
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )


setup_logger()
logger = logging.getLogger("attendance_bot")


def parse_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}

HEADLESS = parse_bool(os.getenv("HEADLESS"), default=False)
ALLOW_INTERACTIVE_LOGIN = parse_bool(
    os.getenv("ALLOW_INTERACTIVE_LOGIN"),
    default=False,
)

CLOSED_SURVEY_PATTERNS = [
    "The survey is now closed.",
    "The survey is closed!",
]


def is_signin_url(url):
    value = (url or "").lower()
    return "signin" in value or "sign_in" in value


def is_authenticated_client_url(url):
    value = (url or "").lower()
    return "app.slack.com/client" in value and not is_signin_url(value)


def click_auth_action_button(page):
    selectors = [
        'button[type="submit"]',
        '[data-qa="signin_button"]',
        'button:has-text("Continue")',
        'button:has-text("Verify")',
        'button:has-text("Submit")',
    ]
    for selector in selectors:
        button = page.locator(selector).first
        try:
            if button.count() > 0 and button.is_visible() and button.is_enabled():
                button.click()
                return True
        except Exception:
            continue
    return False


def wait_for_authenticated_client(page, timeout_s=60):
    target_url = f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}"
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        if is_authenticated_client_url(page.url):
            return True

        if not click_auth_action_button(page):
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
        page.wait_for_timeout(2000)

    return False


def log_state(state, detail=""):
    if detail:
        logger.info("STATE=%s | %s", state, detail)
    else:
        logger.info("STATE=%s", state)


def find_closed_survey_message(page):
    for pattern in CLOSED_SURVEY_PATTERNS:
        locator = page.locator("div.p-rich_text_section", has_text=pattern)
        if locator.count() > 0:
            try:
                return locator.first.inner_text().strip()
            except Exception:
                return pattern
    return None


def capture_debug_artifacts(page):
    screenshot_path = os.getenv("ATTENDANCE_DEBUG_SCREENSHOT", "attendance_debug.png")
    html_path = os.getenv("ATTENDANCE_DEBUG_HTML", "attendance_debug.html")

    try:
        page.screenshot(path=screenshot_path, full_page=True)
        logger.warning("Saved attendance debug screenshot to %s", screenshot_path)
    except Exception:
        pass

    try:
        with open(html_path, "w", encoding="utf-8") as file:
            file.write(page.content())
        logger.warning("Saved attendance debug HTML to %s", html_path)
    except Exception:
        pass


def find_present_option(page):
    candidates = [
        ("input-id", "check", page.locator('input[type="radio"][id*="-present-"]')),
        ("input-value", "check", page.locator('input[type="radio"][value="present"]')),
        (
            "input-aria",
            "check",
            page.locator('input[type="radio"][aria-label*="present" i]'),
        ),
        ("role-radio", "click", page.locator('[role="radio"][aria-label*="present" i]')),
        ("label-text", "click", page.locator('label:has-text("present")')),
    ]

    timeout_s = 25
    start = time.time()
    while time.time() - start < timeout_s:
        for name, action, locator in candidates:
            count = locator.count()
            if count > 0:
                logger.debug("Matched present selector %s (%s elements)", name, count)
                return action, locator, count

        # Slack can lazily render message blocks; keep nudging to latest messages.
        try:
            page.keyboard.press("End")
        except Exception:
            pass
        page.wait_for_timeout(1000)

    return None, None, 0


def handle_security_code_challenge(page):
    # Detect common OTP/code inputs shown after Slack sign-in.
    code_fields = page.locator(
        'input[autocomplete="one-time-code"], '
        'input[inputmode="numeric"], '
        'input[name*="code"], '
        'input[id*="code"]'
    )

    if code_fields.count() == 0:
        return

    log_state("SECURITY_CODE_REQUIRED")

    if not ALLOW_INTERACTIVE_LOGIN:
        raise RuntimeError(
            "Security code required, but ALLOW_INTERACTIVE_LOGIN is false"
        )

    if not os.isatty(0):
        raise RuntimeError(
            "Security code required, but stdin is not interactive. "
            "Run container with -it for bootstrap runs."
        )

    secure_code = input("Enter Slack security code: ").strip()
    if not secure_code:
        raise RuntimeError("Security code was empty")

    field_count = code_fields.count()
    if field_count == 1:
        code_fields.first.fill(secure_code)
    elif len(secure_code) == field_count:
        for idx, char in enumerate(secure_code):
            code_fields.nth(idx).fill(char)
    else:
        # Fallback: many OTP UIs support pasting the full code into first field.
        code_fields.first.fill(secure_code)

    if not click_auth_action_button(page):
        page.keyboard.press("Enter")
    page.wait_for_timeout(3000)


def login_and_save_session():
    # Log into Slack and store session cookies locally
    log_state("LOGIN_REQUIRED", "No valid session found")

    with sync_playwright() as p:
        # Headless mode is controlled through the HEADLESS env variable.
        browser = p.chromium.launch(headless=HEADLESS)

        # Create a fresh browser context (clean session)
        context = browser.new_context()
        page = context.new_page()

        # Open Slack login page
        page.goto("https://wbscodingschool.slack.com/sign_in_with_password")

        # Fill in email and password from .env
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)

        # Click the login button
        page.wait_for_selector('button[type="submit"]', state="visible")
        page.click('[data-qa="signin_button"]')

        # Some Slack logins require a one-time security code.
        page.wait_for_timeout(1500)
        handle_security_code_challenge(page)

        # Validate login on target workspace/channel before saving session.
        if not wait_for_authenticated_client(page, timeout_s=90):
            screenshot_path = os.getenv("LOGIN_DEBUG_SCREENSHOT", "login_failed.png")
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                logger.warning("Saved login debug screenshot to %s", screenshot_path)
            except Exception:
                pass
            raise RuntimeError("Login did not complete; still on sign-in page")

        log_state("LOGIN_AUTHENTICATED")

        # Save session cookies and storage for later reuse
        context.storage_state(path=SESSION_FILE)
        log_state("SESSION_SAVED", SESSION_FILE)

        browser.close()


def is_session_valid():
    # Check if session file exists and is not empty
    if not os.path.exists(SESSION_FILE):
        return False
    if os.path.getsize(SESSION_FILE) == 0:
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            # Load the stored session
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()

            # Open target workspace/channel to verify login.
            page.goto(f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}")
            page.wait_for_load_state("domcontentloaded")

            timeout_s = 25
            start = time.time()
            while time.time() - start < timeout_s:
                if is_authenticated_client_url(page.url):
                    return True
                page.wait_for_timeout(1000)

            return False
        except Exception as exc:
            # Any error -> treat as invalid session
            logger.warning("Session validation failed, will re-login: %s", exc)
            return False
        finally:
            browser.close()


def mark_present():
    # Open the channel and click the newest "present" radio button
    log_state("ATTENDANCE_ATTEMPT_STARTED")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        # Use stored session so no login is needed
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        # Open the Slack channel where the attendance form exists
        page.goto(f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}")

        # Slack can be slow to load
        time.sleep(20)

        closed_message = find_closed_survey_message(page)
        if closed_message:
            log_state("SURVEY_CLOSED", closed_message)
            browser.close()
            return "SURVEY_CLOSED"

        action, present_options, count = find_present_option(page)
        if count == 0:
            closed_message = find_closed_survey_message(page)
            if closed_message:
                log_state("SURVEY_CLOSED", closed_message)
                browser.close()
                return "SURVEY_CLOSED"

            logger.error("STATE=PRESENT_OPTION_NOT_FOUND")
            capture_debug_artifacts(page)
            browser.close()
            return "PRESENT_OPTION_NOT_FOUND"

        # Select the newest "present" option
        newest_present = present_options.nth(count - 1)
        newest_present.scroll_into_view_if_needed()

        # Prepare confirmation message check (from the Mia Attendance Bot)
        confirmation_text = "Your selection (present) has been recorded successfully"
        confirmation_locator = page.locator(
            "div.p-rich_text_section",
            has_text=confirmation_text,
        )
        previous_confirmations = confirmation_locator.count()

        try:
            if action == "check":
                newest_present.check(timeout=5000)
            else:
                newest_present.click(timeout=5000)
        except Exception:
            if action == "check":
                newest_present.check(force=True)
            else:
                newest_present.click(force=True)

        # Wait for the new confirmation message
        confirmed = False
        timeout_s = 15
        start = time.time()
        while time.time() - start < timeout_s:
            if confirmation_locator.count() > previous_confirmations:
                confirmed = True
                break
            time.sleep(0.5)

        if confirmed:
            log_state("PRESENT_RECORDED", confirmation_text)
            # Small delay to ensure the click is registered
            time.sleep(3)
            browser.close()
            return "PRESENT_RECORDED"

        closed_message = find_closed_survey_message(page)
        if closed_message:
            log_state("SURVEY_CLOSED_AFTER_ATTEMPT", closed_message)
            browser.close()
            return "SURVEY_CLOSED"

        logger.warning("STATE=NO_CONFIRMATION_AFTER_CLICK")
        capture_debug_artifacts(page)
        # Small delay to ensure the click is registered
        time.sleep(3)
        browser.close()
        return "NO_CONFIRMATION_AFTER_CLICK"


def ensure_session():
    # Reuse valid session if possible, otherwise login again
    if is_session_valid():
        log_state("SESSION_VALID")
        return True

    if not ALLOW_INTERACTIVE_LOGIN:
        logger.error(
            "STATE=SESSION_INVALID_INTERACTIVE_LOGIN_DISABLED | "
            "Enable ALLOW_INTERACTIVE_LOGIN=true for a bootstrap run."
        )
        return False

    login_and_save_session()
    return is_session_valid()


def run_once():
    # Single run: ensure session exists, then mark attendance
    log_state("RUN_STARTED")
    if not ensure_session():
        log_state("RUN_FAILED", "No valid session")
        raise SystemExit(2)
    attendance_state = mark_present()

    if attendance_state in {"PRESENT_RECORDED", "SURVEY_CLOSED"}:
        log_state("RUN_COMPLETED", attendance_state)
        return

    log_state("RUN_FAILED", attendance_state)
    raise SystemExit(3)


if __name__ == "__main__":
    # Run once and exit (no scheduler / no infinite loop)
    run_once()
