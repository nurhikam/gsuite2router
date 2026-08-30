# Archive - Claude & Codex

Paused 2026-08-31 - bulkag free gak bisa claude/codex via 9Router:

- **Claude:** bulkag4/5 `account on hold` `account_banned` (Anthropic detect bulk), free gak bisa `claude` provider (butuh Pro/Max). `ag/claude-sonnet-4-6` via AG 55x 0/1000 work.
- **Codex:** 0.5.59 `unknown_error` `requestId: f6bcfc59-...` (bug 9Router), bulkag6 ChatGPT `401` `client_id` mismatch `app_X8zY6vW2pQ9tR3dE7nK1jL5gH` vs `app_EMoamEEZ...`.

Wizard: `claude_wizard.py` headed + manual captcha + Gmail magic-link -> code -> Verify -> OAuth
Use `ag/` 55 AG instead: `ag/gemini-3.6-flash`, `ag/claude-sonnet-4-6` via `router.nurhikam.my.id`.

To restore: `mv archive/claude_wizard.py gsuite2router/` + re-add `gsuite2router claude` in `cli.py`.
