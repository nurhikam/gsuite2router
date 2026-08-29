"""9Router REST API client — login, OAuth, provider management."""

import json
import urllib.request
import urllib.error
import ssl


class RouterAPI:
    """HTTP client for 9Router REST API."""

    def __init__(self, base_url, password):
        self.base_url = base_url.rstrip("/")
        self.password = password
        self._cookie = None
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def _request(self, method, path, body=None):
        """Make HTTP request, return (status, data, set_cookie_headers)."""
        url = self.base_url + path
        data = json.dumps(body).encode() if body else None

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        if self._cookie:
            headers["Cookie"] = self._cookie

        req = urllib.request.Request(url, data=data, method=method, headers=headers)

        try:
            resp = urllib.request.urlopen(req, timeout=30, context=self._ctx)
            set_cookie = resp.headers.get_all("Set-Cookie") or []
            raw = resp.read().decode()
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                parsed = raw
            return resp.status, parsed, set_cookie
        except urllib.error.HTTPError as e:
            set_cookie = e.headers.get_all("Set-Cookie") if e.headers else []
            raw = e.read().decode() if e.fp else ""
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                parsed = raw
            return e.code, parsed, set_cookie
        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            if "Connection refused" in reason:
                raise Exception(
                    f"Cannot connect to {self.base_url} — "
                    "make sure 9Router is running"
                )
            raise Exception(f"Request error: {reason}")
        except Exception as e:
            raise Exception(f"Request error: {e}")

    @staticmethod
    def _extract_auth_cookie(set_cookie_headers):
        """Extract auth_token from Set-Cookie headers."""
        for header in set_cookie_headers:
            for part in header.split(";"):
                part = part.strip()
                if part.startswith("auth_token="):
                    return f"auth_token={part.split('=', 1)[1]}"
        return None

    def login(self):
        """Login to 9Router with password, store auth cookie."""
        print("[9Router] Login...")
        status, data, cookies = self._request(
            "POST", "/api/auth/login", {"password": self.password}
        )

        print("[9Router] Login...")
        status, data, cookies = self._request(
            "POST", "/api/auth/login", {"password": self.password}
        )

        if status != 200:
            raise Exception(f"Login failed ({status}): {data}")

        if isinstance(data, dict) and not data.get("success"):
            raise Exception(f"Login failed: {data}")

        cookie = self._extract_auth_cookie(cookies)
        if not cookie:
            raise Exception("auth_token cookie not found in response")

        self._cookie = cookie
        print("[9Router] OK login successful")
        return cookie

    def start_oauth(self, redirect_uri):
        """Start OAuth flow — returns authUrl, codeVerifier, state."""
        import urllib.parse

        path = "/api/oauth/antigravity/authorize?" + urllib.parse.urlencode(
            {"redirect_uri": redirect_uri}
        )
        status, data, _ = self._request("GET", path)

        if status != 200:
            raise Exception(f"Start OAuth failed ({status}): {data}")

        auth_url = data.get("authUrl")
        code_verifier = data.get("codeVerifier")
        state = data.get("state")

        if not all([auth_url, code_verifier, state]):
            raise Exception(f"Incomplete OAuth response: {data}")

        return {"authUrl": auth_url, "codeVerifier": code_verifier, "state": state}

    def exchange_token(self, redirect_uri, code, code_verifier, state):
        """Exchange OAuth auth code for connection."""
        status, data, _ = self._request(
            "POST",
            "/api/oauth/antigravity/exchange",
            {
                "code": code,
                "redirectUri": redirect_uri,
                "codeVerifier": code_verifier,
                "state": state,
            },
        )

        if status not in (200, 201):
            raise Exception(f"Exchange token failed ({status}): {data}")

        return data

    def get_providers(self):
        """Get all provider connections."""
        status, data, _ = self._request("GET", "/api/providers")
        if status != 200:
            raise Exception(f"Get providers failed ({status}): {data}")
        if isinstance(data, dict):
            return data.get("connections", data.get("data", []))
        return data or []

    def get_usage(self, connection_id):
        """Get usage/quota for a connection."""
        status, data, _ = self._request("GET", f"/api/usage/{connection_id}")
        if status != 200:
            return None
        return data

    def delete_provider(self, provider_id):
        """Delete a provider connection."""
        status, _, _ = self._request("DELETE", f"/api/providers/{provider_id}")
        return status == 200

    def reset_provider(self, provider_id):
        """Reset provider status (clear error, set active)."""
        self._request(
            "PUT",
            f"/api/providers/{provider_id}",
            {
                "testStatus": "active",
                "lastError": None,
                "lastErrorAt": None,
                "errorCode": None,
                "backoffLevel": 0,
            },
        )

    def test_provider(self, provider_id):
        """Test/re-verify a provider connection."""
        status, data, _ = self._request(
            "POST", f"/api/providers/{provider_id}/test"
        )
        if status == 200 and isinstance(data, dict):
            return data.get("valid", False), data.get("testStatus", "?")
        return False, "?"
