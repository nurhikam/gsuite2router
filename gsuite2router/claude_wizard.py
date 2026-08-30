"""Wizard: bulk Claude.ai via headed browser + manual captcha + Gmail magic-link.

Flow per akun:
  claude.ai/login -> email -> Enter -> (captcha? PAUSE manual) -> Enter verification code
  -> Gmail (headed) -> Anthropic email -> magic-link -> 6-digit code
  -> claude.ai Verify -> logged in -> 9Router OAuth -> exchange
"""

import re
import html as html_lib
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

from .accounts import read_accounts
from .config import load_config
from .router_api import RouterAPI


def _get_magic_code(ctx, email, password, max_wait=30):
    """Login Gmail headed, find Anthropic magic-link, visit it, return 6-digit code."""
    gmail_page = ctx.new_page()
    gmail_page.goto("https://accounts.google.com/signin/v2/identifier", timeout=15000, wait_until="domcontentloaded")
    time.sleep(2)
    gmail_page.wait_for_selector("#identifierId", timeout=10000)
    gmail_page.fill("#identifierId", email)
    gmail_page.click("#identifierNext")
    gmail_page.wait_for_selector('input[type="password"]', timeout=15000)
    gmail_page.fill('input[type="password"]', password)
    gmail_page.click("#passwordNext")
    time.sleep(5)
    gmail_page.goto("https://mail.google.com", timeout=30000, wait_until="domcontentloaded")
    time.sleep(5)
    gmail_page.reload(wait_until="domcontentloaded")
    time.sleep(5)

    # Find Anthropic email (poll for new email)
    magic_link = None
    for attempt in range(5):
        rows = gmail_page.locator('tr, [role="row"]').all()
        for el in rows:
            try:
                t = el.inner_text().strip()[:100]
                if "Anthropic" in t:
                    el.click(timeout=5000)
                    time.sleep(3)
                    html = gmail_page.content()
                    m = re.search(r'href="([^"]*claude\.ai/magic-link[^"]*)"', html, re.IGNORECASE)
                    if m:
                        magic_link = html_lib.unescape(m.group(1))
                        break
            except Exception:
                continue
        if magic_link:
            break
        print(f"    [Gmail] No Anthropic email yet, retry {attempt+1}/5...")
        time.sleep(3)
        gmail_page.reload(wait_until="domcontentloaded")
        time.sleep(3)

    if not magic_link:
        gmail_page.close()
        return None, "Magic link not found in Gmail"

    magic_page = ctx.new_page()
    magic_page.goto(magic_link, timeout=30000, wait_until="domcontentloaded")
    # Wait for exchange_nonce_for_code to complete (headed needs more time)
    for _ in range(6):
        time.sleep(3)
        html2 = magic_page.content()
        if "verification" in html2.lower():
            break
        if "Loading" in html2 and len(html2) < 5000:
            print(f"    [Gmail] Magic link still loading, waiting...")
            continue
        break
    else:
        html2 = magic_page.content()
    time.sleep(2)
    html2 = magic_page.content()
    code = None
    for m2 in re.finditer(r"\b\d{6}\b", html2):
        ctx_text = html2[max(0, m2.start() - 500):m2.end() + 500]
        if "verification" in ctx_text.lower():
            code = m2.group(0)
            break

    # Check for account on hold
    if "account is on hold" in html2 or "account_banned" in html2:
        magic_page.close()
        gmail_page.close()
        return None, "Account on hold (banned)"

    magic_page.close()
    gmail_page.close()

    if not code:
        return None, "6-digit code not found on magic-link page"
    return code, None


def run_claude_wizard(akun_file="akun.txt", delay=60, url=None, password=None):
    cfg = load_config()
    url = url or cfg["url"]
    password = password or cfg["password"]
    accounts = read_accounts(akun_file)
    print(f"[Wizard] {len(accounts)} accounts from {akun_file}")
    print(f"[Wizard] 9Router: {url}")
    print(f"[Wizard] Mode: headed (manual captcha if needed), delay {delay}s")
    print(f"[Wizard] Browser will stay open for manual captcha. Press Enter in terminal when done.")
    print()

    api = RouterAPI(url, password)
    api.login()
    print(f"[9Router] Login OK")
    print()

    success = 0
    failed = []
    on_hold = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            slow_mo=100,
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="en-US",
        )
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for idx, acc in enumerate(accounts, 1):
            email = acc["email"]
            pw = acc["password"]
            print(f"\n{'='*55}")
            print(f" [{idx}/{len(accounts)}] {email}")
            print(f"{'='*55}")

            try:
                # Step 1: Trigger email on claude.ai
                claude_page = ctx.new_page()
                claude_page.goto("https://claude.ai/login", timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)
                claude_page.locator('[data-testid="email"]').first.fill(email)
                time.sleep(1)
                claude_page.locator('[data-testid="email"]').first.press("Enter")
                time.sleep(5)

                html = claude_page.content()
                if "Too many login attempts" in html:
                    print(f"  [SKIP] Rate limited - Too many login attempts")
                    failed.append((email, "Rate limited"))
                    claude_page.close()
                    if idx < len(accounts):
                        print(f"  [DELAY] {delay}s...")
                        time.sleep(delay)
                    continue

                # Captcha check: Cloudflare or hCaptcha - PAUSE for manual
                captcha_detected = False
                if "challenge" in claude_page.url:
                    captcha_detected = True
                    print(f"  [CAPTCHA] Cloudflare challenge: {claude_page.url[:100]}")
                frames = claude_page.frames
                hcaptcha_frames = [f for f in frames if "hcaptcha" in f.url.lower()]
                if hcaptcha_frames:
                    # Check if hCaptcha is actually showing a challenge (not just invisible)
                    # The challenge frame has id like 0c8y70lphq3, invisible is checkbox-invisible
                    challenge_frames = [f for f in hcaptcha_frames if "challenge" in f.url.lower()]
                    if challenge_frames:
                        captcha_detected = True
                        print(f"  [CAPTCHA] hCaptcha challenge detected ({len(challenge_frames)} frames)")

                if captcha_detected:
                    print(f"  >>> CAPTCHA MUNCUL! <<<")
                    print(f"  >>> Browser keep open - isi captcha di browser (pilih gambar) <<<")
                    print(f"  >>> Tunggu sampai captcha selesai, lalu... <<<")
                    input("  >>> Press Enter di terminal setelah captcha selesai... ")
                    time.sleep(3)
                    # Re-check after manual solve
                    html = claude_page.content()
                    if "challenge" in claude_page.url:
                        print(f"  [WARN] Masih di challenge page setelah manual, tunggu 5s lagi...")
                        time.sleep(5)

                # Verify we're on the right page
                html = claude_page.content()
                if "Enter verification code" not in html and "verification code" not in html.lower():
                    # Check again for captcha after wait
                    html = claude_page.content()
                    if "challenge" in claude_page.url or "hcaptcha" in html.lower():
                        print(f"  [CAPTCHA] Masih ada captcha, pause lagi...")
                        input("  >>> Isi captcha lagi lalu Enter... ")
                        time.sleep(3)
                    html = claude_page.content()
                    if "Enter verification code" not in html:
                        print(f"  [WARN] Not on verification page: {claude_page.url[:100]}")
                        try:
                            print(f"  Body: {claude_page.inner_text('body')[:300]}")
                        except Exception:
                            print(f"  HTML: {html[:500]}")
                        failed.append((email, "Not on verification page"))
                        claude_page.close()
                        continue

                print(f"  [Claude] On verification page, clicking Enter verification code...")
                try:
                    btn = claude_page.locator('[data-testid="enter-code"]').first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click(timeout=5000)
                        time.sleep(2)
                        print(f"  [Claude] Code input shown")
                except Exception as e:
                    print(f"  [WARN] Enter-code click: {e}")

                # Step 2: Get code from Gmail
                print(f"  [Gmail] Fetching magic link for {email}...")
                code, err = _get_magic_code(ctx, email, pw)
                if err:
                    if "on hold" in err.lower() or "banned" in err.lower():
                        print(f"  [SKIP] {err}")
                        on_hold.append(email)
                    else:
                        print(f"  [FAIL] {err}")
                        failed.append((email, err))
                    claude_page.close()
                    if idx < len(accounts):
                        print(f"  [DELAY] {delay}s...")
                        time.sleep(delay)
                    continue

                print(f"  [Gmail] Code: {code}")

                # Step 3: Verify on claude.ai
                print(f"  [Claude] Verifying code {code}...")
                claude_page.locator('[data-testid="code"]').first.fill(code)
                time.sleep(1)
                claude_page.locator('[data-testid="continue"]').first.click(timeout=5000)
                time.sleep(8)

                html = claude_page.content()
                if "account is on hold" in html.lower() or "account_banned" in html:
                    print(f"  [SKIP] Account on hold after verify")
                    on_hold.append(email)
                    claude_page.close()
                    continue

                if "login" in claude_page.url and "Enter verification code" in html:
                    print(f"  [FAIL] Code invalid or expired")
                    failed.append((email, "Invalid code"))
                    claude_page.close()
                    continue

                print(f"  [Claude] URL after verify: {claude_page.url[:100]}")
                if "login" in claude_page.url:
                    print(f"  [FAIL] Still on login page")
                    failed.append((email, "Verify failed - still on login"))
                    claude_page.close()
                    continue

                print(f"  [Claude] Logged in!")

                # Step 4: OAuth to 9Router
                print(f"  [9Router] OAuth authorize...")
                path = "/api/oauth/claude/authorize?" + urllib.parse.urlencode({"redirect_uri": "http://localhost:20128/callback"})
                status, data, _ = api._request("GET", path)
                auth_url = data.get("authUrl", "")
                code_verifier = data.get("codeVerifier", "")
                state = data.get("state", "")

                claude_page.goto(auth_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(5)
                print(f"  [9Router] OAuth URL: {claude_page.url[:120]}")

                if "code=" not in claude_page.url:
                    print(f"  [FAIL] No code in OAuth redirect")
                    html = claude_page.content()
                    print(f"  Body: {claude_page.inner_text('body')[:300] if claude_page.locator('body').count()>0 else html[:500]}")
                    failed.append((email, "No OAuth code"))
                    claude_page.close()
                    continue

                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(claude_page.url)
                oauth_code = parse_qs(parsed.query).get("code", [""])[0]
                print(f"  [9Router] OAuth code: {oauth_code[:30]}...")

                status2, data2, _ = api._request("POST", "/api/oauth/claude/exchange", {
                    "code": oauth_code,
                    "redirectUri": "http://localhost:20128/callback",
                    "codeVerifier": code_verifier,
                    "state": state,
                })
                print(f"  [9Router] Exchange: {status2}")
                if status2 == 200:
                    print(f"  [OK] {email} - Claude added to 9Router!")
                    success += 1
                else:
                    print(f"  [FAIL] Exchange: {data2}")
                    failed.append((email, f"Exchange {status2}: {data2}"))

                claude_page.close()

            except Exception as e:
                print(f"  [FAIL] {email}: {e}")
                import traceback
                traceback.print_exc()
                failed.append((email, str(e)[:100]))
                try:
                    claude_page.close()
                except Exception:
                    pass

            if idx < len(accounts):
                print(f"  [DELAY] {delay}s...")
                time.sleep(delay)

        print(f"\n{'='*55}")
        print(f" DONE!")
        print(f" Success: {success}")
        print(f" On hold: {len(on_hold)} {on_hold[:5]}")
        print(f" Failed: {len(failed)}")
        for em, reason in failed:
            print(f"  - {em}: {reason}")
        print(f"{'='*55}")
        print(f"\nBrowser keep open 10s for inspection...")
        time.sleep(10)
        browser.close()

    return success, failed, on_hold
