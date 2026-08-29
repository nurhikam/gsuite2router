"""CLI interface — main entry point for gsuite2router."""

import os
import sys
import time
import argparse

from . import __version__
from .config import (
    DEFAULT_ROUTER_URL,
    DEFAULT_ROUTER_PASSWORD,
    DEFAULT_REDIRECT_URI,
    DEFAULT_DELAY,
    TIMING,
    load_config,
    save_config,
    get_config_value,
)
from .accounts import read_accounts, remove_account
from .router_api import RouterAPI
from .google_auth import google_login, kill_zombie_browsers, clean_exception
from .delete import run_delete


def format_duration(seconds):
    """Format seconds into readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def print_banner():
    print(r"""
    ___          __  _ ______                 _ __
   /   |  ____  / /_(_) ____/________ __   __(_) /___  __
  / /| | / __ \/ __/ / / __/ ___/ __ `/ | / / / __/ / / /
 / ___ |/ / / / /_/ / /_/ / /  / /_/ /| |/ / / /_/ /_/ /
/_/  |_/_/ /_/\__/_/\____/_/   \__,_/ |___/_/\__/\__, /
                                                 /____/
    """)


def cmd_init(args):
    """Initialize config with router URL and password."""
    print_banner()

    url = args.url or input(f"Router URL [{DEFAULT_ROUTER_URL}]: ").strip() or DEFAULT_ROUTER_URL
    password = args.password or input(f"Router Password [{DEFAULT_ROUTER_PASSWORD}]: ").strip() or DEFAULT_ROUTER_PASSWORD

    config = load_config()
    config["url"] = url
    config["password"] = password
    save_config(config)

    print(f"\nSaved:")
    print(f"  URL      : {url}")
    print(f"  Password : {'*' * len(password)}")


def cmd_add(args):
    """Add accounts to 9Router Antigravity provider."""
    print_banner()

    akun_file = args.file or os.path.join(os.getcwd(), "akun.txt")
    router_url = get_config_value("url", args.url, DEFAULT_ROUTER_URL)
    router_password = get_config_value("password", args.password, DEFAULT_ROUTER_PASSWORD)
    redirect_uri = args.redirect_uri
    speed_mode = "fast" if args.fast else "normal"
    timing = TIMING[speed_mode]

    if not os.path.isabs(akun_file):
        akun_file = os.path.abspath(akun_file)

    print("=" * 55)
    print(f" Router URL    : {router_url}")
    print(f" Speed mode    : {speed_mode.upper()}")
    print(f" Delay         : {args.delay}s")
    print(f" Account file  : {akun_file}")
    print(f" Mode          : API + Browser (Google OAuth only)")
    print("=" * 55)

    kill_zombie_browsers()

    accounts = read_accounts(akun_file)
    if not accounts:
        print("\n [INFO] No accounts to process.")
        print("        Make sure the account file exists and contains: email|password")
        sys.exit(1)

    print(f"\n Total accounts: {len(accounts)}\n")

    api = RouterAPI(router_url, router_password)
    try:
        api.login()
    except Exception as e:
        print(f"\n [ERROR] {e}")
        sys.exit(1)

    success = 0
    fail = 0
    start_time = time.time()

    try:
        for i, account in enumerate(accounts):
            email = account["email"]
            password = account["password"]
            acc_start = time.time()

            print(f"\n{'=' * 55}")
            print(f" [{i + 1}/{len(accounts)}] {email}")
            print(f"{'=' * 55}")

            try:
                print("  [API] OAuth authorize...")
                oauth = api.start_oauth(redirect_uri)

                auth_code = google_login(
                    oauth["authUrl"], email, password, timing, redirect_uri,
                )

                print("  [API] Exchange token...")
                result = api.exchange_token(
                    redirect_uri, auth_code,
                    oauth["codeVerifier"], oauth["state"],
                )

                conn_id = result.get("connection", {}).get("id", "OK")
                acc_elapsed = f"{time.time() - acc_start:.1f}s"
                print(f"\n  [OK] {email} — {conn_id} ({acc_elapsed})")
                success += 1

                try:
                    remove_account(akun_file, account["raw"])
                except Exception:
                    print(f"  [WARN] Failed to remove from account file (permission?)")

            except KeyboardInterrupt:
                raise
            except Exception as e:
                acc_elapsed = f"{time.time() - acc_start:.1f}s"
                print(f"\n  [FAIL] {email}: {clean_exception(e)} ({acc_elapsed})")
                fail += 1

            if i < len(accounts) - 1:
                print(f"\n  [DELAY] Waiting {args.delay}s...")
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print(f"\n\n [INTERRUPTED] Stopped by user (Ctrl+C)")

    total_elapsed = format_duration(time.time() - start_time)
    print(f"\n{'=' * 55}")
    print(f" DONE!")
    print(f" Total   : {len(accounts)} accounts")
    print(f" Success : {success} accounts")
    print(f" Failed  : {fail} accounts")
    print(f" Duration: {total_elapsed}")
    print(f"{'=' * 55}")


def cmd_delete(args):
    """Delete exhausted Antigravity connections from 9Router."""
    print_banner()

    router_url = get_config_value("url", args.url, DEFAULT_ROUTER_URL)
    router_password = get_config_value("password", args.password, DEFAULT_ROUTER_PASSWORD)

    api = RouterAPI(router_url, router_password)
    try:
        api.login()
    except Exception as e:
        print(f"\n [ERROR] {e}")
        sys.exit(1)
    print()

    run_delete(api, dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        prog="gsuite2router",
        description="Auto Add GSuite accounts to 9Router Antigravity provider",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # --- init subcommand ---
    p_init = sub.add_parser("init", help="Initialize config (URL and password)")
    p_init.add_argument("--url", default=None, help="9Router URL")
    p_init.add_argument("--password", default=None, help="9Router password")

    # --- add subcommand ---
    p_add = sub.add_parser("add", help="Add accounts to Antigravity provider")
    p_add.add_argument("--url", default=None, help="9Router URL (overrides config)")
    p_add.add_argument("--password", default=None, help="9Router password (overrides config)")
    p_add.add_argument("--file", default=None, help="Path to account file (default: akun.txt in CWD)")
    p_add.add_argument("--fast", action="store_true", help="Fast mode (good internet, minimal Google delays)")
    p_add.add_argument("--delay", type=int, default=DEFAULT_DELAY, help=f"Delay between accounts in seconds (default: {DEFAULT_DELAY})")
    p_add.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI, help=f"OAuth redirect URI (default: {DEFAULT_REDIRECT_URI})")

    # --- delete subcommand ---
    p_del = sub.add_parser("delete", help="Delete exhausted connections from Antigravity")
    p_del.add_argument("--url", default=None, help="9Router URL (overrides config)")
    p_del.add_argument("--password", default=None, help="9Router password (overrides config)")
    p_del.add_argument("--dry-run", action="store_true", help="Scan only, do not delete")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "delete":
        cmd_delete(args)
    else:
        parser.print_help()
        sys.exit(1)
