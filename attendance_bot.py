from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import time
import os
import logging
from urllib.parse import urlparse

# Slack workspace and channel identifiers
TEAM_ID = "TNS9HAY6M"
CHANNEL_ID = "C09BXD87H54"

# Load credentials from .env file
load_dotenv()
EMAIL = os.getenv("SLACK_EMAIL")
PASSWORD = os.getenv("SLACK_PASSWORD")
SESSION_FILE = os.getenv("SESSION_FILE", "slack_auth.json")
WORKSPACE_DOMAIN = os.getenv("WORKSPACE_DOMAIN", "wbscodingschool.slack.com")
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "").strip()
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


def parse_int(value, default=0):
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default


def unique_nonempty(values):
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


HEADLESS = parse_bool(os.getenv("HEADLESS"), default=False)
ALLOW_INTERACTIVE_LOGIN = parse_bool(
    os.getenv("ALLOW_INTERACTIVE_LOGIN"),
    default=False,
)

CLOSED_SURVEY_PATTERNS = [
    "The survey is now closed.",
    "The survey is closed!",
]

WORKSPACE_SLUG = os.getenv("WORKSPACE_SLUG", WORKSPACE_DOMAIN.split(".")[0]).strip()
if WORKSPACE_SLUG.endswith(".slack.com"):
    WORKSPACE_SLUG = WORKSPACE_SLUG[: -len(".slack.com")]

WORKSPACE_ARCHIVE_URL = f"https://{WORKSPACE_DOMAIN}/archives/{CHANNEL_ID}"
APP_CHANNEL_URL = f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}"
WORKSPACE_SIGNIN_URL = (
    f"https://{WORKSPACE_DOMAIN}/sign_in_with_password"
    f"?redir=%2Farchives%2F{CHANNEL_ID}%3Fname%3D{CHANNEL_ID}"
)
CHANNEL_URLS = [
    APP_CHANNEL_URL,
    WORKSPACE_ARCHIVE_URL,
]
CHANNEL_CONTENT_MARKERS = [
    '[data-qa="message_pane"]',
    '[data-qa="message_content"]',
    "div.c-virtual_list__scroll_container",
    "div.c-virtual_list",
    '[data-qa="channel_header"]',
    '[data-qa="slack_kit_list"]',
    '[data-qa="slack_kit_list_container"]',
]
WORKSPACE_SIGNIN_MAX_ATTEMPTS = int(os.getenv("WORKSPACE_SIGNIN_MAX_ATTEMPTS", "12"))
WORKSPACE_CANDIDATES = unique_nonempty(
    [
        WORKSPACE_SLUG,
        f"{WORKSPACE_SLUG}.slack.com" if WORKSPACE_SLUG else "",
        WORKSPACE_DOMAIN,
        EMAIL,
    ]
)
workspace_signin_attempts = 0
FIND_PRESENT_TIMEOUT_S = int(os.getenv("FIND_PRESENT_TIMEOUT_S", "45"))
AUTH_STABLE_SECONDS = int(os.getenv("AUTH_STABLE_SECONDS", "8"))
SLOW_MO_MS = parse_int(os.getenv("SLOW_MO_MS"), default=0)
DEBUG_NAV_EVENTS = parse_bool(os.getenv("DEBUG_NAV_EVENTS"), default=False)
KEEP_BROWSER_OPEN_SECONDS = parse_int(
    os.getenv("KEEP_BROWSER_OPEN_SECONDS"),
    default=0,
)


def use_persistent_profile():
    return bool(BROWSER_PROFILE_DIR)


def launch_context(playwright, use_saved_state=True):
    if use_persistent_profile():
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            headless=HEADLESS,
            slow_mo=SLOW_MO_MS,
        )
        return None, context

    browser = playwright.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOW_MO_MS,
    )
    if (
        use_saved_state
        and os.path.exists(SESSION_FILE)
        and os.path.getsize(SESSION_FILE) > 0
    ):
        context = browser.new_context(storage_state=SESSION_FILE)
    else:
        context = browser.new_context()
    return browser, context


def close_context(browser, context):
    try:
        if context:
            context.close()
    finally:
        if browser:
            browser.close()


def is_signin_url(url):
    value = (url or "").lower()
    return "signin" in value or "sign_in" in value or "workspace-signin" in value


def get_url_host(url):
    try:
        return urlparse(url or "").netloc.lower()
    except Exception:
        return ""


def is_expected_slack_host(url):
    host = get_url_host(url)
    return host in {"app.slack.com", WORKSPACE_DOMAIN.lower()}


def is_authenticated_client_url(url):
    if not is_expected_slack_host(url):
        return False

    host = get_url_host(url)
    value = (url or "").lower()
    if is_signin_url(value):
        return False

    client_target = f"/client/{TEAM_ID.lower()}/{CHANNEL_ID.lower()}"
    workspace_archive_target = f"/archives/{CHANNEL_ID.lower()}"

    if host == "app.slack.com":
        return client_target in value

    if host == WORKSPACE_DOMAIN.lower():
        return workspace_archive_target in value

    return False


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


def submit_password_login_if_visible(page):
    # Some Slack flows redirect to workspace sign-in again after OTP.
    email_field = page.locator(
        'input[type="email"], input[name="email"], input[id*="email" i]'
    ).first
    password_field = page.locator(
        'input[type="password"], input[name="password"], input[id*="password" i]'
    ).first

    try:
        if email_field.count() == 0 or password_field.count() == 0:
            return False

        if not email_field.is_visible() or not password_field.is_visible():
            return False

        email_field.fill(EMAIL or "")
        password_field.fill(PASSWORD or "")

        if not click_auth_action_button(page):
            page.keyboard.press("Enter")

        page.wait_for_timeout(2000)
        log_state("PASSWORD_LOGIN_SUBMITTED", page.url)
        return True
    except Exception:
        return False


def click_workspace_result_link(page):
    selectors = [
        f'a[href*="{WORKSPACE_DOMAIN}"]',
        f'a[href*="{WORKSPACE_SLUG}.slack.com"]',
        f'a:has-text("{WORKSPACE_SLUG}")',
        'a[href*="/client/"]',
        'a:has-text("Open")',
        'a:has-text("Continue")',
    ]

    for selector in selectors:
        link = page.locator(selector).first
        try:
            if link.count() > 0 and link.is_visible():
                link.click(timeout=3000)
                log_state("WORKSPACE_SIGNIN_LINK_CLICKED", selector)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    return False


def dismiss_open_app_prompt(page):
    # Browser/app handoff prompts can block rendering of the web client.
    selectors = [
        'button:has-text("Use Slack in your browser")',
        'button:has-text("Continue in browser")',
        'button:has-text("Use in browser")',
        'button:has-text("Not now")',
        'button:has-text("Cancel")',
        'a:has-text("Continue in browser")',
    ]
    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(timeout=3000)
                log_state("APP_PROMPT_DISMISSED", selector)
                page.wait_for_timeout(1000)
                return True
        except Exception:
            continue
    return False


def get_workspace_signin_candidates(field):
    try:
        attributes = " ".join(
            [
                field.get_attribute("type") or "",
                field.get_attribute("name") or "",
                field.get_attribute("id") or "",
                field.get_attribute("placeholder") or "",
                field.get_attribute("autocomplete") or "",
            ]
        ).lower()
    except Exception:
        attributes = ""

    # "Find your workspace" often asks for account email instead of workspace slug.
    if "email" in attributes:
        return unique_nonempty([EMAIL])

    return WORKSPACE_CANDIDATES


def handle_workspace_signin(page):
    global workspace_signin_attempts

    if "workspace-signin" not in (page.url or "").lower():
        return False

    if workspace_signin_attempts >= WORKSPACE_SIGNIN_MAX_ATTEMPTS:
        logger.error(
            "STATE=WORKSPACE_SIGNIN_MAX_ATTEMPTS_REACHED | %s",
            WORKSPACE_SIGNIN_MAX_ATTEMPTS,
        )
        return False

    workspace_signin_attempts += 1

    # If Slack shows a workspace result list, prefer clicking a matching result.
    if click_workspace_result_link(page):
        return True

    field = page.locator(
        'input[name*="domain" i], '
        'input[id*="domain" i], '
        'input[data-qa*="workspace" i], '
        'input[placeholder*="workspace" i], '
        'input[type="email"], '
        'input[type="url"], '
        'input[type="text"]'
    ).first

    try:
        if field.count() == 0:
            return False

        submit = page.locator(
            'button[type="submit"], '
            'button:has-text("Continue"), '
            'button:has-text("Next"), '
            'button:has-text("Sign in"), '
            'button:has-text("Find your workspace")'
        ).first

        candidates = get_workspace_signin_candidates(field)
        if not candidates:
            return False

        for candidate in candidates:
            if not candidate:
                continue
            field.fill(candidate)
            if submit.count() > 0 and submit.is_visible():
                submit.click(timeout=3000)
            elif not click_auth_action_button(page):
                page.keyboard.press("Enter")
            page.wait_for_timeout(1500)
            log_state("WORKSPACE_SIGNIN_SUBMITTED", candidate)
            if "workspace-signin" not in (page.url or "").lower():
                return True

        return False
    except Exception:
        return False


def goto_channel(page, timeout_ms=15000):
    for url in CHANNEL_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            dismiss_open_app_prompt(page)
            if is_glitch_page(page):
                log_state("GLITCH_PAGE_DETECTED", page.url)
                continue
            if is_authenticated_client_url(page.url):
                return
            handle_workspace_signin(page)
        except Exception:
            continue


def wait_for_authenticated_client(page, timeout_s=60):
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        goto_channel(page, timeout_ms=15000)

        if wait_for_stable_authenticated_url(page, timeout_s=12):
            return True

        if is_glitch_page(page):
            log_state("GLITCH_PAGE_DETECTED", page.url)
            page.wait_for_timeout(1500)
            continue

        if is_signin_url(page.url):
            log_state("WORKSPACE_SIGNIN_DETECTED", page.url)
            if submit_password_login_if_visible(page):
                page.wait_for_timeout(1500)
                continue
            if handle_workspace_signin(page):
                page.wait_for_timeout(1500)
                continue

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


def maybe_pause_for_debug(reason):
    if KEEP_BROWSER_OPEN_SECONDS <= 0:
        return
    logger.warning(
        "STATE=DEBUG_PAUSE | reason=%s seconds=%s",
        reason,
        KEEP_BROWSER_OPEN_SECONDS,
    )
    time.sleep(KEEP_BROWSER_OPEN_SECONDS)


def attach_page_debug_listeners(page, label="page"):
    if not DEBUG_NAV_EVENTS:
        return

    def on_frame_navigated(frame):
        try:
            if frame == page.main_frame:
                logger.debug("NAV[%s] -> %s", label, frame.url)
        except Exception:
            return

    def on_console(msg):
        try:
            text = msg.text
            if text:
                logger.debug("CONSOLE[%s] %s", label, text)
        except Exception:
            return

    page.on("framenavigated", on_frame_navigated)
    page.on("console", on_console)


def wait_for_stable_authenticated_url(page, timeout_s=20):
    deadline = time.time() + timeout_s
    stable_start = None

    while time.time() < deadline:
        if is_signin_url(page.url) or is_glitch_page(page):
            return False

        if is_authenticated_client_url(page.url):
            if stable_start is None:
                stable_start = time.time()
            if time.time() - stable_start >= AUTH_STABLE_SECONDS:
                return True
        else:
            stable_start = None

        page.wait_for_timeout(1000)

    return False


def is_glitch_page(page):
    try:
        title_text = (page.title() or "").lower()
    except Exception:
        title_text = ""

    if "there's been a glitch" in title_text or "there’s been a glitch" in title_text:
        return True

    try:
        body_text = page.locator("body").inner_text(timeout=1500).lower()
    except Exception:
        return False

    return (
        "there's been a glitch" in body_text
        or "there’s been a glitch" in body_text
    )


def find_closed_survey_message(page, scope=None):
    """Check whether the survey is closed.

    If *scope* is given (a Locator), only look inside that element.
    Otherwise fall back to the full page – but only match the *last*
    occurrence so that an older "closed" banner doesn't shadow a newer
    open survey.
    """
    root = scope if scope is not None else page

    for pattern in CLOSED_SURVEY_PATTERNS:
        locator = root.locator("div.p-rich_text_section", has_text=pattern)
        count = locator.count()
        if count > 0:
            try:
                return locator.nth(count - 1).inner_text().strip()
            except Exception:
                return pattern

    # Fallback: plain-text search inside the scoped root only
    try:
        root_text = root.locator("body").inner_text(timeout=2000) if scope is None else root.inner_text(timeout=2000)
    except Exception:
        root_text = ""

    root_text_lower = root_text.lower()
    for pattern in CLOSED_SURVEY_PATTERNS:
        if pattern.lower() in root_text_lower:
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


def nudge_message_history(page, direction="down"):
    delta_sign = 1 if direction == "down" else -1
    try:
        page.evaluate(
            """(directionSign) => {
                const selectors = [
                    'div.c-virtual_list__scroll_container',
                    '[data-qa="message_pane"]',
                    '[data-qa="slack_kit_list_container"]',
                ];
                for (const selector of selectors) {
                    const node = document.querySelector(selector);
                    if (!node) continue;
                    const step = Math.max(400, Math.floor(node.clientHeight * 0.8));
                    node.scrollTop = node.scrollTop + (directionSign * step);
                }
            }""",
            delta_sign,
        )
    except Exception:
        pass


def get_latest_survey_root(page):
    # Focus the latest survey card from Mia, if present.
    # Try multiple selectors for the survey container, in order of specificity.
    survey_selectors = [
        ('div[role="document"]', "Please select an option"),
        ('div[role="document"]', "present"),
        ('div[data-qa="message_content"]', "Please select an option"),
        ('div[data-qa="message_content"]', "present"),
    ]
    for selector, text in survey_selectors:
        survey_cards = page.locator(selector, has_text=text)
        card_count = survey_cards.count()
        if card_count > 0:
            logger.debug(
                "Found survey cards via %s with text '%s': %s",
                selector, text, card_count,
            )
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
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        dismiss_cookie_or_privacy_overlays(page)

        if has_channel_markers(page):
            return True

        if is_glitch_page(page):
            log_state("CHANNEL_GLITCH_PAGE", page.url)
            return False

        if is_signin_url(page.url):
            log_state("WORKSPACE_SIGNIN_DETECTED", page.url)
            if handle_workspace_signin(page):
                page.wait_for_timeout(1500)
                continue
            log_state("SESSION_REAUTH_REQUIRED", page.url)
            return False

        nudge_to_latest_messages(page)
        # Re-open the channel if Slack navigated away from the target content.
        if not is_authenticated_client_url(page.url):
            goto_channel(page, timeout_ms=15000)
        page.wait_for_timeout(1000)

    return False


def has_channel_markers(page):
    for selector in CHANNEL_CONTENT_MARKERS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
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
        ("text-contains", "click", root.get_by_text("present")),
        ("text-exact", "click", root.get_by_text("present", exact=True)),
        (
            "text-regex",
            "click",
            root.locator(':text-matches("^\\s*present\\s*$", "i")'),
        ),
    ]

    timeout_s = FIND_PRESENT_TIMEOUT_S
    start = time.time()
    while time.time() - start < timeout_s:
        for name, action, locator in candidates:
            count = locator.count()
            if count > 0:
                logger.debug("Matched present selector %s (%s elements)", name, count)
                return action, locator, count

        elapsed = time.time() - start
        # Slack lazily renders content. Start at latest messages, then search upward.
        if elapsed < timeout_s * 0.5:
            nudge_to_latest_messages(page)
            nudge_message_history(page, direction="down")
            try:
                page.keyboard.press("End")
            except Exception:
                pass
        else:
            nudge_message_history(page, direction="up")
            try:
                page.keyboard.press("PageUp")
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

    visible_fields = []
    for idx in range(code_fields.count()):
        field = code_fields.nth(idx)
        try:
            if field.is_visible() and field.is_enabled():
                visible_fields.append(field)
        except Exception:
            continue

    # Slack sometimes renders 6 single-char OTP boxes. If we fill only one box
    # with the whole code, Chromium keeps only the first digit.
    if len(visible_fields) > 1 and len(secure_code) >= len(visible_fields):
        for idx, field in enumerate(visible_fields):
            if idx >= len(secure_code):
                break
            field.fill(secure_code[idx])
    else:
        target = visible_fields[0] if visible_fields else code_fields.first
        target.click()
        try:
            target.fill("")
        except Exception:
            pass
        page.keyboard.type(secure_code, delay=60)

    if not click_auth_action_button(page):
        page.keyboard.press("Enter")
    page.wait_for_timeout(3000)


def login_and_save_session():
    # Log into Slack and store session cookies locally
    log_state("LOGIN_REQUIRED", "No valid session found")

    if not EMAIL or not PASSWORD:
        raise RuntimeError("Missing SLACK_EMAIL or SLACK_PASSWORD in environment")

    with sync_playwright() as p:
        # Create a fresh browser context for login.
        browser, context = launch_context(p, use_saved_state=False)
        page = context.new_page()
        attach_page_debug_listeners(page, label="login")

        # 1) Always start at workspace password page with attendance-channel redirect.
        page.goto(WORKSPACE_SIGNIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        submit_password_login_if_visible(page)

        # 2) OTP challenge after password sign-in.
        page.wait_for_timeout(1500)
        handle_security_code_challenge(page)

        # Slack can ask for password again after OTP redirect.
        submit_password_login_if_visible(page)

        # 3) Ensure auth redirect is fully loaded.
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # 4) Switch to app client, ignore handoff popup, then continue to attendance channel.
        try:
            page.goto(APP_CHANNEL_URL, wait_until="domcontentloaded", timeout=20000)
            dismiss_open_app_prompt(page)
        except Exception:
            pass

        # Try to reach authenticated Slack client before saving session.
        authenticated = wait_for_authenticated_client(page, timeout_s=90)
        if authenticated:
            log_state("LOGIN_AUTHENTICATED")
        else:
            screenshot_path = os.getenv("LOGIN_DEBUG_SCREENSHOT", "login_failed.png")
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                logger.warning("Saved login debug screenshot to %s", screenshot_path)
            except Exception:
                pass
            logger.error("STATE=LOGIN_AUTHENTICATED_NOT_CONFIRMED")
            maybe_pause_for_debug("LOGIN_AUTHENTICATED_NOT_CONFIRMED")
            close_context(browser, context)
            raise RuntimeError("Login not confirmed; refusing to save invalid session")

        # Save session cookies and storage for later reuse
        context.storage_state(path=SESSION_FILE)
        log_state("SESSION_SAVED", SESSION_FILE)
        if use_persistent_profile():
            log_state("PROFILE_SAVED", BROWSER_PROFILE_DIR)

        close_context(browser, context)


def is_session_valid():
    # Check if session file exists and is not empty
    if not os.path.exists(SESSION_FILE):
        return False
    if os.path.getsize(SESSION_FILE) == 0:
        return False

    with sync_playwright() as p:
        browser, context = launch_context(p, use_saved_state=True)
        try:
            # Load stored session/profile
            page = context.new_page()
            attach_page_debug_listeners(page, label="session-check")

            # Open target workspace/channel to verify login.
            goto_channel(page, timeout_ms=15000)
            page.wait_for_load_state("domcontentloaded")

            if is_signin_url(page.url):
                log_state("WORKSPACE_SIGNIN_DETECTED", page.url)
                if handle_workspace_signin(page):
                    page.wait_for_timeout(1500)
                else:
                    log_state("SESSION_INVALID_SIGNIN_URL", page.url)
                    return False

            if is_glitch_page(page):
                log_state("SESSION_INVALID_GLITCH_PAGE", page.url)
                return False

            # Prefer channel-content markers, but accept slow Slack UI when URL stays authenticated.
            if has_channel_markers(page):
                return True

            deadline = time.time() + 15
            while time.time() < deadline:
                dismiss_cookie_or_privacy_overlays(page)
                if is_signin_url(page.url):
                    log_state("WORKSPACE_SIGNIN_DETECTED", page.url)
                    if handle_workspace_signin(page):
                        page.wait_for_timeout(1500)
                        continue
                    log_state("SESSION_REAUTH_REQUIRED", page.url)
                    return False
                if is_glitch_page(page):
                    log_state("SESSION_INVALID_GLITCH_PAGE", page.url)
                    return False
                if has_channel_markers(page):
                    return True
                page.wait_for_timeout(1000)

            log_state("SESSION_VALID_NO_CHANNEL_MARKERS", page.url)

            return True
        except Exception as exc:
            # Any error -> treat as invalid session
            logger.warning("Session validation failed, will re-login: %s", exc)
            return False
        finally:
            close_context(browser, context)


def mark_present():
    # Open the channel and click the newest "present" radio button
    log_state("ATTENDANCE_ATTEMPT_STARTED")

    with sync_playwright() as p:
        # Use stored session/profile so no login is needed
        browser, context = launch_context(p, use_saved_state=True)
        page = context.new_page()
        attach_page_debug_listeners(page, label="attendance")

        # Open the Slack channel where the attendance form exists
        goto_channel(page, timeout_ms=15000)
        log_state("CHANNEL_OPENED", page.url)

        # Wait for Slack to render initial content
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        dismiss_cookie_or_privacy_overlays(page)

        # Try to wait for message pane to render before selector lookups.
        channel_ready = wait_for_channel_content(page, timeout_s=45)
        if not channel_ready and not is_signin_url(page.url):
            logger.warning(
                "Channel markers missing on /client URL, trying archive fallback | url=%s",
                page.url,
            )
            try:
                page.goto(
                    WORKSPACE_ARCHIVE_URL,
                    wait_until="domcontentloaded",
                    timeout=20000,
                )
                log_state("CHANNEL_ARCHIVE_FALLBACK_OPENED", page.url)
            except Exception as exc:
                logger.warning("Archive fallback navigation failed: %s", exc)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            dismiss_cookie_or_privacy_overlays(page)
            channel_ready = wait_for_channel_content(page, timeout_s=35)

        if not channel_ready and is_signin_url(page.url):
            logger.error("STATE=SESSION_REAUTH_REQUIRED | %s", page.url)
            maybe_pause_for_debug("SESSION_REAUTH_REQUIRED")
            close_context(browser, context)
            return "SESSION_REAUTH_REQUIRED"

        if not channel_ready and is_glitch_page(page):
            logger.error("STATE=CHANNEL_GLITCH_PAGE | %s", page.url)
            capture_debug_artifacts(page)
            maybe_pause_for_debug("CHANNEL_GLITCH_PAGE")
            close_context(browser, context)
            return "CHANNEL_GLITCH_PAGE"

        if not channel_ready:
            logger.warning(
                "Message pane selector did not appear within timeout | url=%s",
                page.url,
            )
            try:
                logger.warning("Page title while waiting: %s", page.title())
            except Exception:
                pass
            log_state("CHANNEL_MARKERS_MISSING_CONTINUING", page.url)

        # Always capture a debug screenshot so we can inspect what the bot sees.
        try:
            page.screenshot(path="/session/last_run.png", full_page=True)
            logger.info("STATE=DEBUG_SCREENSHOT_SAVED | /session/last_run.png")
        except Exception as exc:
            logger.warning("Could not save debug screenshot: %s", exc)

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

        # IMPORTANT: Search for the "Present" button FIRST.  The channel
        # may contain *both* an older closed survey AND a newer open one.
        # Only declare "closed" when no clickable option exists at all.
        action, present_options, count = find_present_option(page)
        if count == 0:
            # No present button anywhere — now check if survey is closed.
            survey_root = get_latest_survey_root(page)
            closed_message = find_closed_survey_message(page, scope=survey_root if survey_root is not page else None)
            if closed_message:
                log_state("SURVEY_CLOSED", closed_message)
                maybe_pause_for_debug("SURVEY_CLOSED")
                close_context(browser, context)
                return "SURVEY_CLOSED"

            logger.error("STATE=PRESENT_OPTION_NOT_FOUND")
            capture_debug_artifacts(page)
            maybe_pause_for_debug("PRESENT_OPTION_NOT_FOUND")
            close_context(browser, context)
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
            close_context(browser, context)
            return "PRESENT_RECORDED"

        closed_message = find_closed_survey_message(page)
        if closed_message:
            log_state("SURVEY_CLOSED_AFTER_ATTEMPT", closed_message)
            maybe_pause_for_debug("SURVEY_CLOSED_AFTER_ATTEMPT")
            close_context(browser, context)
            return "SURVEY_CLOSED"

        logger.warning("STATE=NO_CONFIRMATION_AFTER_CLICK")
        capture_debug_artifacts(page)
        maybe_pause_for_debug("NO_CONFIRMATION_AFTER_CLICK")
        # Small delay to ensure the click is registered
        time.sleep(3)
        close_context(browser, context)
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

    try:
        login_and_save_session()
    except Exception as exc:
        logger.error("STATE=LOGIN_FAILED | %s", exc)
        return False

    if is_session_valid():
        log_state("SESSION_VALID_AFTER_LOGIN")
        return True

    logger.error("STATE=SESSION_INVALID_AFTER_LOGIN")
    return False


def run_once():
    global workspace_signin_attempts
    workspace_signin_attempts = 0

    # Single run: ensure session exists, then mark attendance
    log_state("RUN_STARTED")
    logger.info(
        "STATE=RUNTIME_CONFIG | headless=%s slow_mo_ms=%s debug_nav_events=%s",
        HEADLESS,
        SLOW_MO_MS,
        DEBUG_NAV_EVENTS,
    )
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
