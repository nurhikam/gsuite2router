"""Delete exhausted/quota-exceeded Antigravity connections from 9Router."""

import time
from .router_api import RouterAPI


def analyze_connection(connection, usage):
    """Analyze if a connection should be deleted based on error/quota.

    Returns (should_delete: bool, reasons: list[str]).
    """
    reasons = []

    if connection.get("errorCode") == 429:
        reasons.append("error 429 (quota reached)")

    last_error = (connection.get("lastError") or "").lower()
    if "quota" in last_error:
        reasons.append("lastError: quota reached")

    if connection.get("testStatus") == "error":
        reasons.append("testStatus: error")

    if usage and usage.get("quotas"):
        models = usage["quotas"]
        all_exhausted = True
        exhausted_count = 0

        for model_id, quota in models.items():
            if quota.get("unlimited"):
                all_exhausted = False
                continue
            if quota.get("used", 0) >= quota.get("total", 0) or quota.get("remainingPercentage", 1) <= 0:
                exhausted_count += 1
            else:
                all_exhausted = False

        if all_exhausted and len(models) > 0:
            reasons.append(f"all models exhausted ({exhausted_count} model)")

    should_delete = len(reasons) > 0 and (
        any("all models exhausted" in r for r in reasons)
        or (connection.get("errorCode") == 429 and "quota" in (connection.get("lastError") or "").lower())
    )

    return should_delete, reasons


def format_quota_summary(usage):
    """Format quota summary string."""
    if not usage or not usage.get("quotas"):
        return "no usage data"

    models = usage["quotas"]
    exhausted = 0
    active = 0

    for quota in models.values():
        if quota.get("unlimited"):
            active += 1
        elif quota.get("used", 0) >= quota.get("total", 0) or quota.get("remainingPercentage", 1) <= 0:
            exhausted += 1
        else:
            active += 1

    return f"{exhausted} exhausted, {active} active (total {len(models)} model)"


def run_delete(api, dry_run=False):
    """Scan and delete exhausted Antigravity connections.

    Args:
        api: RouterAPI instance (already logged in)
        dry_run: If True, scan only without deleting
    """
    t0 = time.time()
    connections = api.get_providers()
    print(f"Total connections: {len(connections)}\n")

    ag_conns = [
        c for c in connections
        if c.get("provider") in ("antigravity", "ag")
    ]

    print(f"Antigravity connections: {len(ag_conns)}")
    if not ag_conns:
        print("No Antigravity connections found.")
        return

    if dry_run:
        print("\n[DRY RUN] Scan only, will not delete\n")

    print("\nScanning quota...\n")

    to_delete = []
    to_keep = []
    BATCH = 5

    for i in range(0, len(ag_conns), BATCH):
        batch = ag_conns[i : i + BATCH]

        for conn in batch:
            name = conn.get("name") or conn.get("email") or conn.get("displayName") or conn.get("id", "?")

            # Fast path: error 429 + quota
            if conn.get("errorCode") == 429 and "quota" in (conn.get("lastError") or "").lower():
                to_delete.append((conn, ["error 429 (quota reached)"]))
                print(f"  [X] {name} — DELETE (error 429, quota reached)")
                continue

            # Fast path: testStatus error
            if conn.get("testStatus") == "error":
                to_delete.append((conn, ["testStatus: error"]))
                print(f"  [X] {name} — DELETE (testStatus: error)")
                continue

            # Deep check: query usage
            usage = api.get_usage(conn.get("id"))
            should_delete, reasons = analyze_connection(conn, usage)
            summary = format_quota_summary(usage)

            if should_delete:
                to_delete.append((conn, reasons))
                print(f"  [X] {name} — DELETE ({', '.join(reasons)})")
            else:
                to_keep.append(conn)
                print(f"  [OK] {name} — KEEP ({summary})")

    print(f"\n{'—' * 40}")
    print(f"Delete: {len(to_delete)} | Keep: {len(to_keep)}")
    print(f"{'—' * 40}\n")

    if not to_delete:
        print("No connections to delete.")
        return

    if dry_run:
        print("[DRY RUN] Scan complete.")
        return

    # Delete exhausted
    deleted = 0
    failed = 0

    for i in range(0, len(to_delete), BATCH):
        batch = to_delete[i : i + BATCH]
        for conn, reasons in batch:
            name = conn.get("name") or conn.get("email") or conn.get("displayName") or conn.get("id", "?")
            ok = api.delete_provider(conn.get("id"))
            if ok:
                deleted += 1
                print(f"[OK] Deleted: {name}")
            else:
                failed += 1
                print(f"[FAIL] Failed: {name}")

    # Reset kept connections
    if to_keep:
        print(f"\nResetting status for {len(to_keep)} active accounts...\n")
        for conn in to_keep:
            name = conn.get("name") or conn.get("email") or conn.get("displayName") or conn.get("id", "?")
            api.reset_provider(conn.get("id"))
            valid, status = api.test_provider(conn.get("id"))
            new_status = "active" if valid else status
            print(f"  [~] {name} — status: {new_status}")

    elapsed = f"{time.time() - t0:.1f}s"
    print(f"\n{'=' * 40}")
    print(f"Done! Deleted: {deleted} | Failed: {failed} | Reset: {len(to_keep)} | Time: {elapsed}")
    print(f"{'=' * 40}")
