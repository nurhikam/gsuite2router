"""Archive: Codex wizard (paused).

Codex via 9Router 0.5.59 `unknown_error` + bulkag ChatGPT `401` client_id mismatch.
Use `ag/` 55 AG instead. See archive/README.md.

Kept for reference - not wired to CLI.
"""

# Placeholder - full wizard was not built (only Claude wizard was).
# Codex needs: chatgpt.com headed -> Google OAuth -> Allow -> about-you age 25 -> ChatGPT
# Then extract accessToken via /api/auth/session and inject to 9Router DB as codex provider.
# But 9Router 0.5.59 Codex OAuth `auth.openai.com/oauth/authorize` returns unknown_error
# even before Google login, so bulk Codex via 9Router is blocked upstream.

# To restore: build codex_wizard.py similar to claude_wizard.py and wire `gsuite2router codex`.
