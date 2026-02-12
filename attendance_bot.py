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
WORKSPACE_DOMAIN = os.getenv("WORKSPACE_DOMAIN", "wbscodingschool.slack.com")
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

WORKSPACE_SLUG = os.getenv("WORKSPACE_SLUG", WORKSPACE_DOMAIN.split(".")[0])
CHANNEL_URLS = [
    f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}",
    f"https://{WORKSPACE_DOMAIN}/archives/{CHANNEL_ID}",
]


def is_signin_url(url):
    value = (url or "").lower()
    return "signin" in value or "sign_in" in value or "workspace-signin" in value


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


def handle_workspace_signin(page):
    if "workspace-signin" not in (page.url or "").lower():
        return False

    field = page.locator(
        'input[name*="domain" i], '
        'input[id*="domain" i], '
        'input[data-qa*="workspace" i], '
        'input[placeholder*="workspace" i], '
        'input[type="url"], '
        'input[type="text"]'
    ).first

    try:
        if field.count() == 0:
            return False
        field.fill(WORKSPACE_SLUG)
        submit = page.locator(
            'button[type="submit"], '
            'button:has-text("Continue"), '
            'button:has-text("Next"), '
            'button:has-text("Sign in")'
        ).first
        if submit.count() > 0 and submit.is_visible():
            submit.click(timeout=3000)
        elif not click_auth_action_button(page):
            page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        log_state("WORKSPACE_SIGNIN_SUBMITTED", WORKSPACE_SLUG)
        return True
    except Exception:
        return False


def goto_channel(page, timeout_ms=15000):
    for url in CHANNEL_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if is_authenticated_client_url(page.url):
                return
            handle_workspace_signin(page)
        except Exception:
            continue


def wait_for_authenticated_client(page, timeout_s=60):
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        goto_channel(page, timeout_ms=15000)

        if is_authenticated_client_url(page.url) and wait_for_channel_content(page, timeout_s=12):
            return True

        handle_workspace_signin(page)
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
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
    except Exception:
        body_text = ""

    body_text_lower = body_text.lower()
    for pattern in CLOSED_SURVEY_PATTERNS:
        if pattern.lower() in body_text_lower:
            return pattern

        locator = page.locator("div.p-rich_text_section", has_text=pattern)
        if locator.count() > 0:
            try:
                return locator.first.inner_text().strip()
            except Exception:
                return pattern
    return None


def nudge_to_latest_messages(page):
    # Slack renders inside nested scroll containers; scroll all of them down.
    try:
        page.evaluate(
            """() => {
                const nodes = Array.from(document.querySelectorAll("*"));
                for (const node of nodes) {
                    if (node.scrollHeight > node.clientHeight) {
                        node.scrollTop = node.scrollHeight;
                    }
                }
                window.scrollTo(0, document.body.scrollHeight);
            }"""
        )
    except Exception:
        pass


def get_latest_survey_root(page):
    # Focus the latest survey card from Mia, if present.
    survey_cards = page.locator('div[role="document"]', has_text="Please select an option")
    card_count = survey_cards.count()
    if card_count > 0:
        logger.debug("Found survey cards: %s", card_count)
        return survey_cards.nth(card_count - 1)
    return page


def dismiss_cookie_or_privacy_overlays(page):
    selectors = [
        "#onetrust-accept-btn-handler",
        'button:has-text("Accept All")',
        'button:has-text("Accept all")',
        'button:has-text("Allow all")',
        'button:has-text("I agree")',
        'button:has-text("I Accept")',
    ]

    for frame in page.frames:
        for selector in selectors:
            try:
                button = frame.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    log_state("COOKIE_BANNER_DETECTED", selector)
                    button.click(timeout=3000)
                    page.wait_for_timeout(1200)
                    log_state("COOKIE_BANNER_ACCEPTED", selector)
                    return True
            except Exception:
                continue

    return False


def wait_for_channel_content(page, timeout_s=45):
    markers = [
        '[data-qa="message_pane"]',
        '[data-qa="message_content"]',
        "div.c-virtual_list__scroll_container",
        '[data-qa="channel_header"]',
    ]
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        dismiss_cookie_or_privacy_overlays(page)

        for selector in markers:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        if is_signin_url(page.url):
            log_state("WORKSPACE_SIGNIN_DETECTED", page.url)
            handled = handle_workspace_signin(page)
            if handled:
                goto_channel(page, timeout_ms=15000)
                page.wait_for_timeout(1000)
                continue
            return False

        nudge_to_latest_messages(page)
        # Re-open the channel if Slack navigated away from the target content.
        if not is_authenticated_client_url(page.url):
            goto_channel(page, timeout_ms=15000)
        page.wait_for_timeout(1000)

    return False


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
    root = get_latest_survey_root(page)

    candidates = [
        ("role-radio-text", "click", root.locator('[role="radio"]:has-text("present")')),
        ("role-radio-aria", "click", root.locator('[role="radio"][aria-label*="present" i]')),
        ("button-text", "click", root.locator('button:has-text("present")')),
        ("aria-any", "click", root.locator('[aria-label*="present" i]')),
        ("label-text", "click", root.locator('label:has-text("present")')),
        ("input-id", "check", root.locator('input[type="radio"][id*="-present-"]')),
        ("input-value", "check", root.locator('input[type="radio"][value="present"]')),
        ("input-aria", "check", root.locator('input[type="radio"][aria-label*="present" i]')),
        ("text-exact", "click", root.get_by_text("present", exact=True)),
        (
            "text-regex",
            "click",
            root.locator(':text-matches("^\\s*present\\s*$", "i")'),
        ),
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
        nudge_to_latest_messages(page)
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
        page.goto(f"https://{WORKSPACE_DOMAIN}/sign_in_with_password")

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
            goto_channel(page, timeout_ms=15000)
            page.wait_for_load_state("domcontentloaded")

            if not is_authenticated_client_url(page.url):
                return False

            # Session is valid only when real channel content is available.
            return wait_for_channel_content(page, timeout_s=20)
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
        goto_channel(page, timeout_ms=15000)
        log_state("CHANNEL_OPENED", page.url)

        # Slack can be slow to load
        time.sleep(20)
        dismiss_cookie_or_privacy_overlays(page)

        # Try to wait for message pane to render before selector lookups.
        if not wait_for_channel_content(page, timeout_s=45):
            logger.warning(
                "Message pane selector did not appear within timeout | url=%s",
                page.url,
            )
            try:
                logger.warning("Page title while waiting: %s", page.title())
            except Exception:
                pass
            logger.error("STATE=CHANNEL_CONTENT_NOT_AVAILABLE")
            capture_debug_artifacts(page)
            browser.close()
            return "CHANNEL_CONTENT_NOT_AVAILABLE"

        try:
            body_text = page.locator("body").inner_text(timeout=3000).lower()
            prompt_present = "please select an option" in body_text
            closed_present = "the survey is now closed." in body_text or "the survey is closed!" in body_text
            log_state(
                "SURVEY_TEXT_SCAN",
                f"prompt_present={prompt_present} closed_present={closed_present}",
            )
        except Exception:
            logger.warning("Failed to read body text for survey text scan")

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
