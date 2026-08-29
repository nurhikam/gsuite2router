# gsuite2router

Bulk-add Google (GSuite) accounts to the **Antigravity** provider on a [9Router](https://9router.ai) instance via its REST API, with browser automation only for Google OAuth login.

## How It Works

```
9Router API                          Google OAuth (browser)
───────────                          ─────────────────────
POST /api/auth/login ──► auth cookie
GET  /api/oauth/authorize ──► authUrl ──► Chrome opens ──► email/password ──► consent ──► auth code
POST /api/oauth/exchange  ◄── code ◄──────────────────────────────────────────────────────┘
```

- **9Router** interaction is done entirely via REST API (fast, no fragile CSS selectors).
- **Google OAuth** login is done via browser (DrissionPage + Chrome) because Google blocks programmatic login.
- Each account gets a **fresh browser profile** (temp directory) — your existing Chrome profile is never touched.

## Requirements

- Python 3.8+
- Google Chrome installed
- 9Router instance running (local or remote)

## Installation

```bash
git clone https://github.com/mhiqrambg/gsuite2router.git
cd gsuite2router

python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -e .
```

## Quick Start

### 1. Initialize config

Save your 9Router URL and password so you don't have to type them every time.

```bash
# Interactive
gsuite2router init

# Or pass directly
gsuite2router init --url http://localhost:20128 --password 'yourpassword'
```

Config is saved to `.gs2router.json` in the current directory.

> **Note:** If your password contains special characters (`&`, `%`, `@`, `!`), wrap it in **single quotes**.

### 2. Create account file

Create `akun.txt` in the current directory with one account per line:

```
user1@yourdomain.com|password123
user2@yourdomain.com|password456
user3@yourdomain.com|password789
```

Format: `email|password`

### 3. Add accounts

```bash
gsuite2router add
```

The tool will:
1. Login to 9Router via API
2. For each account, open Chrome, login to Google, handle consent pages
3. Exchange the OAuth code via API to create a connection
4. Remove successfully added accounts from `akun.txt`

### 4. Delete exhausted accounts (optional)

Scan for and remove Antigravity connections that have hit quota limits:

```bash
# Scan and delete
gsuite2router delete

# Scan only (dry run)
gsuite2router delete --dry-run
```

## Commands

### `gsuite2router init`

Initialize config with router URL and password.

```
Options:
  --url URL            9Router URL (default: http://localhost:20128)
  --password PASSWORD  9Router password (default: 123456)
```

### `gsuite2router add`

Add accounts from `akun.txt` to the Antigravity provider.

```
Options:
  --url URL             9Router URL (overrides config)
  --password PASSWORD   9Router password (overrides config)
  --file FILE           Path to account file (default: akun.txt in CWD)
  --fast                Fast mode (good internet, minimal delays)
  --delay DELAY         Delay between accounts in seconds (default: 3)
  --redirect-uri URI    OAuth redirect URI (default: http://localhost:20128/callback)
```

### `gsuite2router delete`

Delete exhausted/quota-exceeded Antigravity connections.

```
Options:
  --url URL             9Router URL (overrides config)
  --password PASSWORD   9Router password (overrides config)
  --dry-run             Scan only, do not delete
```

## Examples

```bash
# Basic usage (reads URL/password from .gs2router.json)
gsuite2router add

# Fast mode with custom delay
gsuite2router add --fast --delay 1

# Use a different account file
gsuite2router add --file /path/to/accounts.txt

# Override config for a one-off run
gsuite2router add --url http://192.168.1.100:20128 --password 'otherpass'

# Dry-run delete (scan only)
gsuite2router delete --dry-run
```

## Config Priority

Values are resolved in this order:

1. **CLI argument** (e.g. `--url`, `--password`)
2. **Config file** (`.gs2router.json`)
3. **Default** (`http://localhost:20128`, `123456`)

## Project Structure

```
gsuite2router/
├── gsuite2router/
│   ├── __init__.py       # Version
│   ├── __main__.py       # python -m gsuite2router
│   ├── cli.py            # CLI (init/add/delete subcommands)
│   ├── config.py         # Constants, timing profiles, config file I/O
│   ├── router_api.py     # 9Router REST API client
│   ├── google_auth.py    # Google OAuth via DrissionPage
│   ├── accounts.py       # Account file read/write
│   └── delete.py         # Quota scan + delete exhausted
├── requirements.txt
├── setup.py
├── akun.txt              # Account file (email|password)
└── .gs2router.json       # Saved config (gitignored)
```

## Troubleshooting

**"Cannot connect to ... make sure 9Router is running"**
- 9Router is not running or the URL is wrong. Check with `curl <url>/api/auth/login`.

**"Login failed (403): error code: 1010"**
- Cloudflare is blocking the request. This is handled automatically with proper User-Agent headers.

**"redirect_uri_mismatch"**
- The OAuth redirect URI doesn't match what's registered in Google Cloud Console. Use `--redirect-uri` to override.

**Permission denied on akun.txt**
- The file is owned by root. Fix with `sudo chown $USER akun.txt`.

**Password with special characters**
- Always wrap passwords in single quotes: `--password 'my&pass%word'`
