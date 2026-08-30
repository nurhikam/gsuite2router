# Archive - Codex dan Claude gabisa

Paused 2026-08-31 - Codex dan Claude gabisa via bulkag free + 9Router:

- **Claude gabisa:** bulkag4/5 `account on hold` `account_banned` (Anthropic detect bulk), free gak bisa `claude` provider (butuh Pro/Max). `ag/claude-sonnet-4-6` via AG 55x 0/1000 work.
- **Codex gabisa:** 0.5.59 `unknown_error` `requestId: f6bcfc59-...` (bug 9Router), bulkag6 ChatGPT `401` `client_id` mismatch `app_X8zY6vW2pQ9tR3dE7nK1jL5gH` vs `app_EMoamEEZ...`.

Wizard: `claude_wizard.py` headed + manual captcha + Gmail magic-link -> code -> Verify -> OAuth
Use `ag/` 55 AG instead: `ag/gemini-3.6-flash`, `ag/claude-sonnet-4-6` via `router.nurhikam.my.id`.

## Riset A & B — kenapa gabisa

**A. Claude `claude.ai` via `bulkag` free:**
- Google SSO GIS `gsi/transform` `postMessage` `code` ke-capture (`4/0ATsMZq...`) tapi `COOP` block di `headless=True` → main `claude.ai/login` gak navigasi. Manual `POST` GIS code → `403 Just a moment` Cloudflare.
- Email `Continue with email` → `challenge_redirect` Turnstile stuck headless, bahkan stealth `navigator.webdriver` bypass. Headed `headless=False` work (`bulkag2` tanpa challenge, `bulkag4` headed OK), tapi bulk trigger → `Too many login attempts` + `account on hold` `account_banned` (Anthropic detect bulk IP `114.10.75.180`).
- Gmail IMAP `AUTHENTICATIONFAILED` semua 55 (Workspace `Less Secure Apps` disabled), `gmail.readonly` OAuth `restricted_client` `Unregistered scope` untuk Antigravity client `1071006060591`.
- Magic-link `https://claude.ai/magic-link#hash:base64(email)` → `POST /api/auth/exchange_nonce_for_code` `200` → `Use verification code to continue` `442784`/`609398`/`711322` work headed, tapi bulk `bulkag4`/`bulkag5` `account on hold` 2:41 AM. Free plan gak bisa `claude` provider (butuh Pro/Max).

**B. Codex `auth.openai.com` / `chatgpt.com` via `bulkag` free:**
- `9Router` `0.5.59` `GET /api/oauth/codex/authorize` → `https://auth.openai.com/oauth/authorize?client_id=app_EMoamEEZ...` langsung `error?payload=...` `unknown_error` `requestId: f6bcfc59-...` sebelum Google login — bug 9Router, bukan bulkag. `0.5.55` juga sama.
- `chatgpt.com` headed work: `Continue with Google` → `bulkag6` → `Allow` → `about-you` `age 25` (via `focus()` + `keyboard.type`) → `ChatGPT` `Where should we begin?` ✅. Tapi `9Router` Codex butuh `client_id` `app_EMoamEEZ...`, ChatGPT token `app_X8zY6vW2pQ9tR3dE7nK1jL5gH` → `401 Unauthorized` + `400 The 'gpt-5.6' model is not supported when using Codex with a ChatGPT account.` + `429 usage limit` untuk `cx/gpt-5.5`.
- `Bulk Add Codex Accounts` butuh `accessToken` + `refreshToken` + `idToken` JSON, tapi `chatgpt.com/api/auth/session` cuma kasih `accessToken` tanpa `refreshToken` `rt.1.AAD...`.

**Kesimpulan:** `bulkag` free paling worth `ag/` 55x `0/1000` — `ag/gemini-3.6-flash`, `ag/claude-sonnet-4-6` via `router.nurhikam.my.id` verified `Hello`. Claude/Codex native free gak bisa bulk.

## Alasan (kenapa di-archive)

- **Claude:** Anthropic `on hold` karena bulk signup dari IP sama `114.10.75.180` dalam menit — `unusual activity` → `Request a review` 10 hari. Free plan `claude` provider di 9Router cuma untuk Pro/Max, free gak dapet quota. `ag/claude` via Antigravity gak perlu Pro, 55x `0/1000` work.
- **Codex:** 9Router Codex OAuth `unknown_error` bukan salah bulkag — `auth.openai.com` `AuthApiFailure` bahkan sebelum Google login, `0.5.55` dan `0.5.59` sama. ChatGPT `bulkag6` headed work tapi token `client_id` beda (`app_X8zY6vW2p...` vs `app_EMoamEEZ...`) → `401`/`400`/`429` di `cx/`. `Bulk Add` butuh `refreshToken` yang gak ada.
- **Effort vs gain:** Claude butuh `headed` + manual `hCaptcha` + Gmail `magic-link` + `60s` delay per akun, Codex butuh fix upstream 9Router. Sementara `ag/` 55 AG udah `Hello` tanpa captcha/hold.

**Alasan archive:** simpan wizard buat referensi, tapi pause bulk — fokus `ag/` yang proven.

To restore: `mv archive/claude_wizard.py gsuite2router/` + re-add `gsuite2router claude` in `cli.py`.
