"""Google OAuth login via DrissionPage — anti-detection, text-based locators."""

import time
import tempfile
import shutil
import random
from urllib.parse import urlparse, parse_qs
from DrissionPage._units.actions import Keys

from .config import CHROME_ARGS


def clean_exception(e):
    """Convert any DrissionPage internal error messages into clean English."""
    msg = str(e).strip()
    if "页面被刷新" in msg or "加载完成" in msg:
        return "Page was navigating/reloading during action"
    if "没有找到" in msg:
        return "Element not found on page"
    if "连接" in msg and "断开" in msg:
        return "Browser connection disconnected"
    if "版本:" in msg:
        msg = msg.split("版本:")[0].strip()
    return msg


def _find_element(tab, locators, timeout=3):
    """Find element from list of locators, return first found or None."""
    for locator in locators:
        try:
            ele = tab.ele(locator, timeout=timeout)
            if ele:
                return ele
        except Exception:
            continue
    return None


def _find_and_click(tab, locators, timeout=3):
    """Find and click element from list of locators."""
    for locator in locators:
        try:
            ele = tab.ele(locator, timeout=timeout)
            if ele:
                try:
                    ele.click()
                    return True
                except Exception:
                    try:
                        ele.click(by_js=True)
                        return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def _force_input(tab, locator_or_ele, text, timeout=10, desc="field"):
    """Input text with 4-layer fallback strategy. Accepts element directly or locator(s)."""
    if hasattr(locator_or_ele, "input"):
        ele = locator_or_ele
    elif isinstance(locator_or_ele, (list, tuple)):
        ele = _find_element(tab, locator_or_ele, timeout=timeout)
    else:
        ele = _find_element(tab, [locator_or_ele], timeout=timeout)

    if ele is None:
        raise Exception(f"Element {desc} not found: {locator_or_ele}")

    def _has_value():
        try:
            val = ele.attr("value") or ele.property("value") or ele.run_js("return this.value;") or ""
            return text in val or len(val) == len(text) or len(val) > 0
        except Exception:
            return False

    # Strategy 1: .input() standard
    try:
        ele.input(text, clear=True)
        time.sleep(0.3)
        if _has_value():
            return ele
    except Exception:
        pass

    # Strategy 2: .input(by_js=True)
    try:
        ele.input(text, clear=True, by_js=True)
        time.sleep(0.3)
        if _has_value():
            return ele
    except Exception:
        pass

    # Strategy 3: CDP keyboard input
    try:
        ele.click()
        time.sleep(0.2)
        tab.actions.key_down(Keys.CTRL).type("a").key_up(Keys.CTRL)
        time.sleep(0.1)
        tab.actions.type(Keys.BACKSPACE)
        time.sleep(0.1)
        tab.actions.type(text)
        time.sleep(0.3)
        if _has_value():
            return ele
    except Exception:
        pass

    # Strategy 4: Raw JavaScript with full event simulation
    try:
        ele.click()
        time.sleep(0.2)
        ele.run_js(
            """
            this.focus();
            this.value = arguments[0];
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            text,
        )
        time.sleep(0.3)
        return ele
    except Exception:
        pass

    raise Exception(f"Failed to input text to {desc} with all strategies")


def _extract_code_from_url(url):
    """Extract OAuth code from URL query parameter."""
    if not url or "code=" not in url:
        return None
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        codes = params.get("code", [])
        return codes[0] if codes else None
    except Exception:
        return None


def _check_redirect(tab, redirect_uri):
    """Check if current URL is the callback redirect with auth code."""
    try:
        url = tab.url
        if redirect_uri:
            uri_clean = redirect_uri.split("://", 1)[-1].rstrip("/")
            if uri_clean in url:
                return _extract_code_from_url(url)
        if "code=" in url and ("callback" in url or "localhost" in url):
            return _extract_code_from_url(url)
    except Exception:
        pass
    return None


def _check_google_errors(tab):
    """Check if Google displayed an actual blocking error message on the page."""
    try:
        err = tab.run_js("""
            const errKeywords = [
                "couldn't find your google account",
                "tidak dapat menemukan akun google",
                "enter a valid email",
                "masukkan email yang valid",
                "wrong password",
                "sandi salah",
                "too many failed attempts",
                "terlalu banyak upaya",
                "account disabled",
                "akun dinonaktifkan",
                "cannot sign you in",
                "tidak dapat membuat anda login"
            ];
            const errEls = document.querySelectorAll(
                'div[aria-live="assertive"], div.jssense, div[jsname="B1fAeb"], .Ekjuhf, .dEOOab, .o6cuMc'
            );
            for (const el of errEls) {
                const text = (el.innerText || el.textContent || '').toLowerCase().trim();
                for (const kw of errKeywords) {
                    if (text.includes(kw)) {
                        return (el.innerText || el.textContent || '').trim();
                    }
                }
            }
            return null;
        """)
        return err
    except Exception:
        return None


def _wait_for_password_field(tab, max_timeout=15):
    """Dynamically poll for password input until it appears and is ready."""
    start_time = time.time()
    while time.time() - start_time < max_timeout:
        for loc in [
            'input[type="password"]',
            'input[name="Passwd"]',
            '@type=password',
            '@name=Passwd',
            'tag:input@@type=password',
            'tag:input@@name=Passwd',
        ]:
            try:
                ele = tab.ele(loc, timeout=0.3)
                if ele:
                    is_visible = ele.run_js("return this.offsetParent !== null;")
                    if is_visible:
                        return ele
            except Exception:
                continue

        err = _check_google_errors(tab)
        if err:
            raise Exception(f"Google error: {err}")

        time.sleep(0.3)

    return None


def _handle_consent_loop(tab, timing, redirect_uri=None, email=None, password=None):
    """Handle Google consent / confirmation / account picker pages until OAuth redirect happens."""
    MAX_STEPS = 25
    tos_accepted = False

    for step in range(1, MAX_STEPS + 1):
        try:
            # 1. Check redirect for auth code
            code = _check_redirect(tab, redirect_uri)
            if code:
                return code

            try:
                current_url = tab.url
            except Exception:
                time.sleep(1)
                code = _check_redirect(tab, redirect_uri)
                if code:
                    return code
                return None

            # Left Google domain = redirect in progress / completed
            if "accounts.google.com" not in current_url and "google.com" not in current_url:
                code = _extract_code_from_url(current_url)
                if code:
                    return code
                time.sleep(1)
                try:
                    code = _extract_code_from_url(tab.url)
                    if code:
                        return code
                except Exception:
                    pass
                return code

            print(f"        [Step {step}] URL: {current_url[:80]}")

            # -------------------------------------------------------------
            # SPECIAL CASE 1: Workspace Terms of Service ("Welcome to your new account")
            # Click ONCE and wait for Google backend to finish provisioning.
            # -------------------------------------------------------------
            if ("workspacetermsofservice" in current_url or "speedbump" in current_url) and not tos_accepted:
                print("        >> Workspace Terms of Service detected")
                tos_clicked = tab.run_js("""
                    window.scrollTo(0, document.body.scrollHeight);
                    const candidates = [
                        '#gaplustosNext button',
                        '#gaplustosNext input[type="submit"]',
                        '#gaplustosNext input',
                        '#gaplustosNext',
                        'input[type="submit"]',
                    ];
                    for (const sel of candidates) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) {
                            el.click();
                            return 'tos_sel:' + sel;
                        }
                    }
                    const btn = Array.from(document.querySelectorAll('button, input[type="submit"], div[role="button"]'))
                        .find(el => {
                            const t = (el.innerText || el.value || el.textContent || '').toLowerCase();
                            return t.includes('i understand') || t.includes('saya memahami') || t.includes('accept') || t.includes('saya setuju');
                        });
                    if (btn) {
                        btn.click();
                        return 'tos_text';
                    }
                    return null;
                """)

                if tos_clicked:
                    tos_accepted = True
                    print(f"        >> Accepted TOS ({tos_clicked}) — waiting for Google backend...")
                    # Dynamic wait for page to transition away from TOS
                    for _ in range(8):
                        time.sleep(0.5)
                        code = _check_redirect(tab, redirect_uri)
                        if code:
                            return code
                        try:
                            if "workspacetermsofservice" not in tab.url and "speedbump" not in tab.url:
                                break
                        except Exception:
                            break
                    continue

            # If still on TOS after clicking, just wait for Google server without re-clicking
            if "workspacetermsofservice" in current_url or "speedbump" in current_url:
                print("        >> Waiting for Workspace TOS provisioning...")
                time.sleep(1.5)
                continue

            # -------------------------------------------------------------
            # SPECIAL CASE 2: Unknown Error page (Google glitch recovery)
            # -------------------------------------------------------------
            if "unknownerror" in current_url:
                print("        >> Google unknownerror page — clicking continue/retry...")
                tab.run_js("""
                    const btn = Array.from(document.querySelectorAll('button, a, input[type="submit"], div[role="button"]'))
                        .find(el => el.offsetParent !== null);
                    if (btn) btn.click();
                """)
                time.sleep(2)
                continue

            # -------------------------------------------------------------
            # SPECIAL CASE 3: Account Chooser / Select Account page
            # -------------------------------------------------------------
            is_account_chooser = (
                "accountchooser" in current_url
                or "chooseaccount" in current_url
                or "selectaccount" in current_url
            )

            if is_account_chooser:
                print("        >> Account Chooser detected")
                account_clicked = tab.run_js("""
                    const targetEmail = (arguments[0] || '').toLowerCase().trim();
                    const username = targetEmail.split('@')[0];

                    const accountItems = Array.from(
                        document.querySelectorAll('li, div[role="link"], div[role="button"], div.J1DgEc, a')
                    ).filter(el => el.offsetParent !== null);

                    const found = accountItems.find(el => {
                        const t = (el.innerText || el.textContent || '').toLowerCase();
                        const isNotAnother = !t.includes('use another account') && !t.includes('gunakan akun lain');
                        const matches = t.includes(targetEmail) || (username.length > 4 && t.includes(username));
                        return isNotAnother && matches;
                    });

                    if (found) {
                        found.scrollIntoView();
                        found.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        found.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        found.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        found.click();
                        return 'account_card:' + targetEmail;
                    }
                    return null;
                """, email or "")

                if account_clicked:
                    print(f"        >> Selected account ({account_clicked})")
                    time.sleep(2)
                    # Check if password is requested again
                    try:
                        pwd_box = tab.ele('input[type="password"]', timeout=2)
                        if pwd_box and password:
                            print("        >> Password requested on account select, re-entering...")
                            _force_input(tab, pwd_box, password, timeout=5, desc="password re-entry")
                            _find_and_click(tab, ["#passwordNext", "tag:button@@text():Next", "tag:button@@text():Berikutnya"], timeout=2)
                            time.sleep(2)
                    except Exception:
                        pass
                    code = _check_redirect(tab, redirect_uri)
                    if code:
                        return code
                    continue

            # -------------------------------------------------------------
            # GENERAL CASE: Consent / Permissions / Submit Action Buttons
            # -------------------------------------------------------------
            clicked = tab.run_js("""
                // 1. Auto-check any unchecked consent checkboxes
                document.querySelectorAll('input[type="checkbox"]:not(:checked)')
                    .forEach(cb => cb.click());

                // 2. High-priority ID selectors (Allow, Consent, Confirm, Approve)
                const prioritySelectors = [
                    '#submit_approve_access button',
                    '#submit_approve_access',
                    '#confirm',
                    '#next button',
                    '#next',
                    'input[type="submit"]',
                ];
                for (const sel of prioritySelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) {
                        el.click();
                        return 'id:' + sel;
                    }
                }

                // 3. Action text search across all buttons, links, and submit inputs
                const actionKeywords = [
                    'allow', 'izinkan',
                    'continue', 'lanjutkan',
                    'sign in', 'masuk',
                    'accept', 'terima',
                    'i agree', 'saya setuju',
                    'confirm', 'konfirmasi',
                    'next', 'berikutnya',
                    'i understand', 'saya memahami', 'saya mengerti',
                ];

                const candidates = Array.from(
                    document.querySelectorAll('button, a, input[type="submit"], div[role="button"], span[role="button"]')
                ).filter(el => el.offsetParent !== null);

                for (const kw of actionKeywords) {
                    const found = candidates.find(el => {
                        const t = (el.innerText || el.value || el.textContent || '').toLowerCase().trim();
                        return t === kw || t.includes(kw);
                    });
                    if (found) {
                        found.click();
                        return 'action_text:' + kw;
                    }
                }

                return null;
            """)

            if clicked:
                print(f"        >> Clicked ({clicked})")
                time.sleep(timing["after_consent_btn"])
                code = _check_redirect(tab, redirect_uri)
                if code:
                    return code
                continue

            # Fallback to DrissionPage locator search
            locators_to_try = [
                "#submit_approve_access",
                "tag:button@@text():Allow",
                "tag:button@@text():Izinkan",
                "tag:button@@text():Continue",
                "tag:button@@text():Lanjutkan",
                "tag:button@@text():Sign in",
                "tag:button@@text():Masuk",
                "tag:button@@text():I understand",
                "tag:button@@text():Saya memahami",
                "tag:button@@text():Accept",
                "tag:input@@type=submit",
            ]
            dp_clicked = _find_and_click(tab, locators_to_try, timeout=0.8)
            if dp_clicked:
                print("        >> Button clicked (via DrissionPage locator)")
                time.sleep(timing["after_consent_btn"])
                code = _check_redirect(tab, redirect_uri)
                if code:
                    return code
                continue

            # No button found on this step — wait briefly
            time.sleep(timing["no_btn_wait"])

            code = _check_redirect(tab, redirect_uri)
            if code:
                return code

        except Exception as e:
            # Handle DrissionPage DOM context reload / page navigation in progress
            err_str = str(e)
            if "页面" in err_str or "refresh" in err_str.lower() or "context" in err_str.lower() or "lost" in err_str.lower() or "disconnected" in err_str.lower():
                time.sleep(1)
                code = _check_redirect(tab, redirect_uri)
                if code:
                    return code
                continue
            raise Exception(clean_exception(e))

    raise Exception(
        f"Too many Google confirmation steps ({MAX_STEPS}x) — "
        "possibly stuck on an unknown page"
    )


def google_login(auth_url, email, password, timing, redirect_uri):
    """Login to Google OAuth via DrissionPage. Returns auth code.

    Creates a fresh ChromiumPage per account for full session isolation.
    Each page gets its own temp user data dir (cleaned up after).
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    tmp_dir = tempfile.mkdtemp(prefix="gs2r_")

    co = ChromiumOptions()
    for arg in CHROME_ARGS:
        co.set_argument(arg)
    co.set_user_data_path(tmp_dir)
    co.set_local_port(random.randint(19200, 29200))

    page = ChromiumPage(co)

    try:
        print(f"  [Google] Navigate...")
        page.get(auth_url)
        time.sleep(timing["google_initial"])

        # Check for auto-redirect (already logged in)
        code = _check_redirect(page, redirect_uri)
        if code:
            print(f"  [Google] OK auth code (auto-redirect)")
            return code

        # -------------------------------------------------------------
        # STEP 1: Email Input & Submit
        # -------------------------------------------------------------
        print(f"  [Google] Email...")
        _force_input(page, "#identifierId", email, timeout=15, desc="email field")
        time.sleep(timing["after_email_input"])

        # Submit email: Click Next or press Enter
        email_submitted = _find_and_click(page, [
            "#identifierNext",
            "tag:button@@text():Next",
            "tag:button@@text():Berikutnya",
            "tag:button@@text():Lanjutkan",
        ], timeout=2)

        if not email_submitted:
            try:
                page.actions.type(Keys.ENTER)
                email_submitted = True
            except Exception:
                pass

        if not email_submitted:
            raise Exception("Next button (email) not found")

        # -------------------------------------------------------------
        # STEP 2: Wait & Input Password
        # -------------------------------------------------------------
        print(f"  [Google] Waiting for password page...")
        pwd_input = _wait_for_password_field(page, max_timeout=timing["password_timeout"])
        if not pwd_input:
            raise Exception("Password field did not appear within timeout")

        print(f"  [Google] Password...")
        _force_input(page, pwd_input, password, timeout=5, desc="password field")
        time.sleep(timing["after_pw_input"])

        # Submit password: Click Next or press Enter
        pwd_submitted = _find_and_click(page, [
            "#passwordNext",
            "tag:button@@text():Next",
            "tag:button@@text():Berikutnya",
            "tag:button@@text():Lanjutkan",
        ], timeout=2)

        if not pwd_submitted:
            try:
                page.actions.type(Keys.ENTER)
                pwd_submitted = True
            except Exception:
                pass

        if not pwd_submitted:
            raise Exception("Next button (password) not found")

        time.sleep(timing["after_pw_next"])

        # -------------------------------------------------------------
        # STEP 3: Handle Consent & OAuth Redirection
        # -------------------------------------------------------------
        print(f"  [Google] Consent...")
        code = _handle_consent_loop(page, timing, redirect_uri=redirect_uri, email=email, password=password)
        if code:
            print(f"  [Google] OK auth code obtained")
            return code

        # Final wait & redirect check
        time.sleep(timing["redirect_wait"])
        try:
            current_url = page.url
            code = _extract_code_from_url(current_url)
            if code:
                print(f"  [Google] OK auth code obtained")
                return code
        except Exception:
            pass

        raise Exception("Auth code not captured")

    except Exception as e:
        raise Exception(clean_exception(e))

    finally:
        try:
            page.quit()
        except Exception:
            pass
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def kill_zombie_browsers():
    """Kill leftover Chrome processes from previous runs."""
    import os
    import glob
    import subprocess

    if os.name == "nt":
        return

    try:
        subprocess.run(
            ["pkill", "-f", "chrome.*gs2r_"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass

    for old_tmp in glob.glob(os.path.join(tempfile.gettempdir(), "gs2r_*")):
        try:
            shutil.rmtree(old_tmp, ignore_errors=True)
        except Exception:
            pass
