from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import time
import os

# Slack workspace and channel identifiers
TEAM_ID = "TNS9HAY6M"
CHANNEL_ID = "C09BXD87H54"

# Load credentials from .env file
load_dotenv()
EMAIL = os.getenv("SLACK_EMAIL")
PASSWORD = os.getenv("SLACK_PASSWORD")
SESSION_FILE = os.getenv("SESSION_FILE", "slack_auth.json")


def parse_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}

HEADLESS = parse_bool(os.getenv("HEADLESS"), default=False)
ALLOW_INTERACTIVE_LOGIN = parse_bool(
    os.getenv("ALLOW_INTERACTIVE_LOGIN"),
    default=False,
)


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
    print("🔐 No session found - logging into Slack")

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
                print(f"WARN: Saved login debug screenshot to {screenshot_path}")
            except Exception:
                pass
            raise RuntimeError("Login did not complete; still on sign-in page")

        # Save session cookies and storage for later reuse
        context.storage_state(path=SESSION_FILE)
        print("✅ Slack session saved")

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
            print(f"WARN: Session validation failed, will re-login: {exc}")
            return False
        finally:
            browser.close()


def mark_present():
    # Open the channel and click the newest "present" radio button
    print("🟢 Marking attendance as PRESENT")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        # Use stored session so no login is needed
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        # Open the Slack channel where the attendance form exists
        page.goto(f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}")

        # Slack can be slow to load
        time.sleep(20)

        # Find all "present" radio buttons
        present_radios = page.locator('input[type="radio"][id$="-present-0"]')

        # If none are found, stop
        count = present_radios.count()
        if count == 0:
            print("❌ No present buttons found")
            browser.close()
            return

        # Click the newest "present" option
        newest_present = present_radios.nth(count - 1)
        newest_present.scroll_into_view_if_needed()

        # Prepare confirmation message check (from the Mia Attendance Bot)
        confirmation_text = "Your selection (present) has been recorded successfully"
        confirmation_locator = page.locator(
            "div.p-rich_text_section",
            has_text=confirmation_text,
        )
        previous_confirmations = confirmation_locator.count()

        newest_present.check()

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
            print("✅ Attendance recorded: confirmation message detected")
        else:
            print("⚠️ Attendance clicked, but confirmation message not found")

        # Small delay to ensure the click is registered
        time.sleep(3)
        browser.close()


def ensure_session():
    # Reuse valid session if possible, otherwise login again
    if is_session_valid():
        print("🔑 Existing Slack session found")
        return True

    if not ALLOW_INTERACTIVE_LOGIN:
        print(
            "❌ Session invalid and interactive login disabled. "
            "Enable ALLOW_INTERACTIVE_LOGIN=true for a bootstrap run."
        )
        return False

    login_and_save_session()
    return is_session_valid()


def run_once():
    # Single run: ensure session exists, then mark attendance
    print("⏰ Attendance run started")
    if not ensure_session():
        raise SystemExit(2)
    mark_present()


if __name__ == "__main__":
    # Run once and exit (no scheduler / no infinite loop)
    run_once()
