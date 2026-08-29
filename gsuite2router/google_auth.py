"""Google OAuth login via DrissionPage — anti-detection, text-based locators."""

import time
import tempfile
import shutil
import random
from urllib.parse import urlparse, parse_qs

from .config import CHROME_ARGS


def _find_element(tab, locators, timeout=5):
    """Find element from list of locators, return first found or None."""
    for locator in locators:
        try:
            ele = tab.ele(locator, timeout=timeout)
            if ele:
                return ele
        except Exception:
            continue
    return None


def _find_and_click(tab, locators, timeout=5):
    """Find and click element from list of locators."""
    ele = _find_element(tab, locators, timeout=timeout)
    if ele:
        ele.click()
        return True
    return False


def _force_input(tab, locator, text, timeout=15, desc="field"):
    """Input text with 4-layer fallback strategy."""
    ele = _find_element(tab, [locator], timeout=timeout)
    if ele is None:
        raise Exception(f"Element {desc} not found: {locator}")

    # Strategy 1: .input() standard
    try:
        ele.input(text, clear=True)
        time.sleep(0.5)
        val = ele.attr("value") or ele.property("value") or ""
        if text in val:
            return ele
    except Exception:
        pass

    # Strategy 2: .input(by_js=True)
    try:
        ele.input(text, clear=True, by_js=True)
        time.sleep(0.5)
        val = ele.attr("value") or ele.property("value") or ""
        if text in val:
            return ele
    except Exception:
        pass

    # Strategy 3: CDP keyboard input
    try:
        from DrissionPage._units.actions import Keys

        ele.click()
        time.sleep(0.3)
        tab.actions.key_down(Keys.CTRL).type("a").key_up(Keys.CTRL)
        time.sleep(0.2)
        tab.actions.type(Keys.BACKSPACE)
        time.sleep(0.3)
        tab.actions.input(text)
        time.sleep(0.5)
        val = ele.attr("value") or ele.property("value") or ""
        if text in val:
            return ele
    except Exception:
        pass

    # Strategy 4: Raw JavaScript
    try:
        ele.click()
        time.sleep(0.3)
        ele.run_js(
            """
            this.focus();
            this.value = arguments[0];
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            text,
        )
        time.sleep(0.5)
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
        if redirect_uri.split("://", 1)[-1] in url:
            return _extract_code_from_url(url)
    except Exception:
        pass
    return None


def _handle_consent_loop(tab, timing, redirect_uri=None):
    """Handle Google consent pages in a loop. Returns auth code or None."""
    MAX_STEPS = 10

    for step in range(1, MAX_STEPS + 1):
        time.sleep(timing["step_loop_wait"])

        if redirect_uri:
            code = _check_redirect(tab, redirect_uri)
            if code:
                return code

        try:
            current_url = tab.url
        except Exception:
            return None

        if "accounts.google.com" not in current_url and "google.com" not in current_url:
            code = _extract_code_from_url(current_url)
            return code

        print(f"        [Step {step}] URL: {current_url[:80]}")

        # Workspace Terms of Service
        if "workspacetermsofservice" in current_url or "speedbump" in current_url:
            clicked = _find_and_click(tab, [
                "tag:button@@text():I understand",
                "tag:button@@text():I Understand",
                "tag:button@@text():Accept",
                "tag:input@@type=submit",
            ], timeout=timing["tos_button_timeout"])

            if not clicked:
                clicked = tab.run_js("""
                    window.scrollTo(0, document.body.scrollHeight);
                    const btn = Array.from(document.querySelectorAll('button, input[type="submit"]'))
                        .find(el => {
                            const t = (el.innerText || el.value || '').toLowerCase();
                            return t.includes('i understand') || t.includes('accept');
                        });
                    if (btn) { btn.click(); return true; }
                    return false;
                """)

            if clicked:
                print("        >> 'I understand' (Workspace TOS) clicked!")
                time.sleep(timing["after_tos_click"])
                continue

        # Continue button
        clicked = _find_and_click(tab, [
            "tag:button@@text():Continue",
        ], timeout=timing["btn_find_timeout"])
        if clicked:
            print("        >> 'Continue' clicked!")
            time.sleep(timing["after_consent_btn"])
            continue

        # I Understand
        clicked = _find_and_click(tab, [
            "#gaplustosNext",
            "tag:button@@text():I Understand",
            "tag:button@@text():I understand",
            "tag:button@@text():I agree",
            "tag:a@@text():I Understand",
            "tag:a@@text():I understand",
        ], timeout=timing["btn_find_timeout"])
        if clicked:
            print("        >> 'I Understand' clicked!")
            time.sleep(timing["after_consent_btn"])
            continue

        # Allow
        clicked = _find_and_click(tab, [
            "#submit_approve_access",
            "tag:button@@text():Allow",
        ], timeout=timing["btn_find_timeout"])
        if clicked:
            print("        >> 'Allow' clicked!")
            time.sleep(timing["after_allow"])
            continue

        # Check unchecked checkboxes
        try:
            tab.run_js("""
                document.querySelectorAll('input[type="checkbox"]:not(:checked)')
                    .forEach(cb => cb.click());
            """)
        except Exception:
            pass

        # JS fallback
        clicked = tab.run_js("""
            const keywords = [
                'i understand', 'continue', 'allow', 'accept',
                'i agree', 'confirm', 'next',
            ];
            const btn = Array.from(document.querySelectorAll('button, a, input[type="submit"]'))
                .find(el => {
                    const text = (el.innerText || el.value || el.textContent || '').toLowerCase().trim();
                    return keywords.some(kw => text.includes(kw));
                });
            if (btn) { btn.click(); return true; }
            return false;
        """)
        if clicked:
            print("        >> Button clicked (via JS fallback)!")
            time.sleep(timing["after_consent_btn"])
            continue

        print(f"        >> [WAIT] No button found, waiting...")
        time.sleep(timing["no_btn_wait"])

    raise Exception(
        f"Too many Google confirmation steps ({MAX_STEPS}x) — "
        "possibly stuck on an unknown page"
    )


def google_login(auth_url, email, password, timing, redirect_uri):
    """Login to Google OAuth via DrissionPage. Returns auth code.

    Creates a fresh ChromiumPage per account for full session isolation.
    Each page gets its own temp user data dir (cleaned up after).

    Args:
        auth_url: Google OAuth URL from 9Router API
        email: Google email
        password: Google password
        timing: Timing profile dict
        redirect_uri: OAuth redirect URI for code capture

    Returns:
        Auth code string
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

        try:
            current_url = page.url
            code = _extract_code_from_url(current_url)
            if code:
                print(f"  [Google] OK auth code (auto-redirect)")
                return code
        except Exception:
            pass

        # Input email
        print(f"  [Google] Email...")
        _force_input(page, "#identifierId", email, timeout=15, desc="email field")
        time.sleep(timing["after_email_input"])

        # Click Next (email)
        if not _find_and_click(page, [
            "#identifierNext",
            "tag:button@@text():Next",
        ], timeout=5):
            raise Exception("Next button (email) not found")

        print(f"  [Google] Waiting for password page...")
        time.sleep(timing["after_email_next"])

        # Password field
        print(f"  [Google] Password...")
        pw_done = False
        for loc in [
            "@type=password",
            "tag:input@@type=password",
            "@name=Passwd",
            "tag:input@@name=Passwd",
        ]:
            try:
                _force_input(page, loc, password, timeout=5, desc="password field")
                pw_done = True
                break
            except Exception:
                continue
        if not pw_done:
            try:
                page.run_js("""
                    const inp = document.querySelector('input[type="password"]');
                    if (inp) {
                        inp.focus();
                        inp.value = arguments[0];
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                """, password)
                pw_done = True
            except Exception:
                pass
        if not pw_done:
            raise Exception("Password field not found")
        time.sleep(timing["after_pw_input"])

        # Click Next (password)
        if not _find_and_click(page, [
            "#passwordNext",
            "tag:button@@text():Next",
        ], timeout=5):
            raise Exception("Next button (password) not found")
        time.sleep(timing["after_pw_next"])

        # Handle consent pages
        print(f"  [Google] Consent...")
        code = _handle_consent_loop(page, timing, redirect_uri=redirect_uri)
        if code:
            print(f"  [Google] OK auth code obtained")
            return code

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
