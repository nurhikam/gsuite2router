"""Google OAuth login via Playwright — headless, WSL-friendly."""

import time
from urllib.parse import urlparse, parse_qs


def clean_exception(e):
    msg = str(e).strip()
    if "Timeout" in msg and "waiting for" in msg:
        return f"Timeout: {msg[:200]}"
    return msg


def _extract_code_from_url(url):
    if not url or "code=" not in url:
        return None
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        codes = params.get("code", [])
        return codes[0] if codes else None
    except Exception:
        return None


def _check_redirect(page, redirect_uri):
    try:
        url = page.url
        if redirect_uri:
            uri_clean = redirect_uri.split("://", 1)[-1].rstrip("/")
            if uri_clean in url:
                return _extract_code_from_url(url)
        if "code=" in url and ("callback" in url or "localhost" in url):
            return _extract_code_from_url(url)
    except Exception:
        pass
    return None


def _check_google_errors(page):
    """Check for blocking Google error messages."""
    try:
        text = page.inner_text("body").lower() if page.locator("body").count() > 0 else ""
        keywords = [
            "couldn't find your google account",
            "tidak dapat menemukan akun google",
            "wrong password", "sandi salah",
            "too many failed attempts", "terlalu banyak upaya",
            "account disabled", "akun dinonaktifkan",
        ]
        for kw in keywords:
            if kw in text:
                # extract the error line
                for line in text.split("\n"):
                    if kw in line:
                        return line.strip()[:300]
                return kw
    except Exception:
        pass
    return None


def _handle_consent_loop(page, timing, redirect_uri=None):
    MAX_STEPS = 25
    tos_accepted = False

    for step in range(1, MAX_STEPS + 1):
        code = _check_redirect(page, redirect_uri)
        if code:
            return code

        try:
            url = page.url
        except Exception:
            time.sleep(1)
            code = _check_redirect(page, redirect_uri)
            if code:
                return code
            return None

        if "accounts.google.com" not in url and "google.com" not in url:
            code = _extract_code_from_url(url)
            if code:
                return code
            time.sleep(1)
            try:
                code = _extract_code_from_url(page.url)
                if code:
                    return code
            except Exception:
                pass
            return code

        print(f"        [Step {step}] URL: {url[:80]}")

        # TOS
        if ("workspacetermsofservice" in url or "speedbump" in url) and not tos_accepted:
            print("        >> Workspace TOS detected")
            clicked = False
            for sel in ['button:has-text("I understand")', 'button:has-text("Saya memahami")', 'button:has-text("Accept")', '#gaplustosNext button', '#gaplustosNext']:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(timeout=3000)
                        clicked = True
                        print(f"        >> Accepted TOS ({sel})")
                        break
                except Exception:
                    continue
            if clicked:
                tos_accepted = True
                # Wait for TOS to transition — it goes to OAuth consent, not directly to redirect
                for _ in range(10):
                    time.sleep(0.5)
                    code = _check_redirect(page, redirect_uri)
                    if code:
                        return code
                    try:
                        if "workspacetermsofservice" not in page.url and "speedbump" not in page.url:
                            break
                    except Exception:
                        break
                # After TOS, we're on OAuth consent — don't wait, continue to consent handler
                continue

        if "workspacetermsofservice" in url or "speedbump" in url:
            # Already accepted TOS but still on TOS page — Google is slow, wait briefly then try clicking again
            print("        >> Waiting for TOS provisioning...")
            # Try clicking I understand again if visible
            try:
                btn = page.locator('button:has-text("I understand")').first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=3000)
                    print("        >> Re-clicked I understand")
                    time.sleep(2)
                    continue
            except Exception:
                pass
            time.sleep(1.5)
            continue

        if "unknownerror" in url:
            print("        >> unknownerror — retry")
            try:
                btn = page.locator("button, a, div[role='button']").first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=2000)
            except Exception:
                pass
            time.sleep(2)
            continue

        # Account chooser
        if "accountchooser" in url or "chooseaccount" in url or "selectaccount" in url:
            print("        >> Account chooser — looking for account")
            time.sleep(1)
            continue

        # General consent buttons — including OAuth "Sign in" for Antigravity
        clicked = None
        for sel in [
            '#submit_approve_access',
            '#submit_approve_access button',
            'button:has-text("Sign in")',
            'button:has-text("Masuk")',
            'button:has-text("Allow")',
            'button:has-text("Izinkan")',
            'button:has-text("Continue")',
            'button:has-text("Lanjutkan")',
            'button:has-text("Accept")',
            'button:has-text("I agree")',
            'button:has-text("Saya setuju")',
            'input[type="submit"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=3000)
                    clicked = sel
                    print(f"        >> Clicked ({sel})")
                    break
            except Exception:
                continue

        # Also try generic "Sign in" if above didn't match (OAuth consent page)
        if not clicked:
            try:
                # The OAuth consent has "Sign in" button that may not match has-text exactly
                for btn in page.locator("button").all():
                    try:
                        txt = btn.inner_text().strip().lower()
                        if txt == "sign in" or txt == "masuk":
                            if btn.is_visible():
                                btn.click(timeout=3000)
                                clicked = f"button:Sign in"
                                print(f"        >> Clicked (Sign in generic)")
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        if clicked:
            time.sleep(timing.get("after_consent_btn", 1.5))
            code = _check_redirect(page, redirect_uri)
            if code:
                return code
            continue

        time.sleep(timing.get("no_btn_wait", 1.5))
        code = _check_redirect(page, redirect_uri)
        if code:
            return code

    raise Exception(f"Too many consent steps ({MAX_STEPS}x) — stuck")


def google_login_playwright(auth_url, email, password, timing, redirect_uri):
    """Login via Playwright. Returns auth code."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--no-first-run",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        try:
            print("  [Google] Navigate...")
            page.goto(auth_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(timing.get("google_initial", 1.5))

            code = _check_redirect(page, redirect_uri)
            if code:
                print("  [Google] OK auth code (auto-redirect)")
                return code

            # Email
            print("  [Google] Email...")
            page.wait_for_selector("#identifierId", timeout=15000)
            page.fill("#identifierId", email)
            time.sleep(timing.get("after_email_input", 0.5))
            page.click("#identifierNext")
            print("  [Google] Waiting for password page...")

            # Wait for password field
            try:
                page.wait_for_selector('input[type="password"]', timeout=timing.get("password_timeout", 15) * 1000)
            except Exception:
                err = _check_google_errors(page)
                if err:
                    raise Exception(f"Google error: {err}")
                raise Exception("Password field did not appear within timeout")

            print("  [Google] Password...")
            page.fill('input[type="password"]', password)
            time.sleep(timing.get("after_pw_input", 0.5))
            page.click("#passwordNext")
            time.sleep(timing.get("after_pw_next", 1.5))

            # Check for wrong password immediately
            time.sleep(2)
            err = _check_google_errors(page)
            if err and ("wrong password" in err.lower() or "sandi salah" in err.lower()):
                raise Exception(f"Google error: {err}")

            print("  [Google] Consent...")
            code = _handle_consent_loop(page, timing, redirect_uri=redirect_uri)
            if code:
                print("  [Google] OK auth code obtained")
                return code

            time.sleep(timing.get("redirect_wait", 1.5))
            code = _extract_code_from_url(page.url)
            if code:
                print("  [Google] OK auth code obtained")
                return code

            raise Exception("Auth code not captured")

        except Exception as e:
            raise Exception(clean_exception(e))
        finally:
            try:
                browser.close()
            except Exception:
                pass


def kill_zombie_browsers():
    pass
