"""Single-user OAuth for the public MCP endpoint.

ChatGPT/Claude register themselves (dynamic client registration), send you to
a one-page login where you type your passphrase once, and then hold a token.
Everything is stored in the state DB so restarts don't log you out.
"""

from __future__ import annotations

import hmac
import html
import secrets
import time
from collections import deque
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from wardrobe.state import State

SCOPE = "wardrobe"
ACCESS_TTL = 7 * 86400
REFRESH_TTL = 365 * 86400
CODE_TTL = 300
PENDING_TTL = 900


PAGE_HEADERS = {"X-Frame-Options": "DENY", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


class PassphraseOAuthProvider:
    def __init__(self, state: State, public_url: str, passphrase: str):
        self.state = state
        self.public_url = public_url
        self._passphrase = passphrase
        self._failures: deque[float] = deque()

    # ------------------------------------------------------------ clients

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = self.state.oauth_get("client", client_id)
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        assert client_info.client_id
        self.state.oauth_put("client", client_info.client_id, client_info.model_dump(mode="json"), None)

    # ------------------------------------------------------------ authorize

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        request_id = secrets.token_urlsafe(24)
        self.state.oauth_put(
            "pending",
            request_id,
            {"client_id": client.client_id, "client_name": client.client_name, "params": params.model_dump(mode="json")},
            time.time() + PENDING_TTL,
        )
        return f"{self.public_url}/login?req={request_id}"

    def _too_many_failures(self) -> bool:
        cutoff = time.time() - 900
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        return len(self._failures) >= 10

    async def login_page(self, request: Request) -> Response:
        if request.method == "GET":
            request_id = request.query_params.get("req", "")
            pending = self.state.oauth_get("pending", request_id)
            if not pending:
                return HTMLResponse(_page("This sign-in link has expired. Start again from the app."), status_code=400, headers=PAGE_HEADERS)
            return HTMLResponse(_login_form(request_id, pending.get("client_name") or "An app"), headers=PAGE_HEADERS)

        form = await request.form()
        request_id = str(form.get("req", ""))
        passphrase = str(form.get("passphrase", ""))
        pending = self.state.oauth_get("pending", request_id)
        if not pending:
            return HTMLResponse(_page("This sign-in link has expired. Start again from the app."), status_code=400, headers=PAGE_HEADERS)
        if self._too_many_failures():
            return HTMLResponse(_page("Too many wrong attempts. Wait 15 minutes."), status_code=429, headers=PAGE_HEADERS)
        if not hmac.compare_digest(passphrase.encode(), self._passphrase.encode()):
            self._failures.append(time.time())
            return HTMLResponse(_login_form(request_id, pending.get("client_name") or "An app", error=True), status_code=401, headers=PAGE_HEADERS)

        self.state.oauth_delete("pending", request_id)
        params = AuthorizationParams.model_validate(pending["params"])
        code = AuthorizationCode(
            code=secrets.token_urlsafe(32),
            scopes=params.scopes or [SCOPE],
            expires_at=time.time() + CODE_TTL,
            client_id=pending["client_id"],
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="owner",
        )
        self.state.oauth_put("code", code.code, code.model_dump(mode="json"), code.expires_at)
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code.code, state=params.state), status_code=302)

    # ------------------------------------------------------------ tokens

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> AuthorizationCode | None:
        data = self.state.oauth_get("code", authorization_code)
        if not data or data["client_id"] != client.client_id:
            return None
        return AuthorizationCode.model_validate(data)

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        now = int(time.time())
        access = AccessToken(
            token=secrets.token_urlsafe(32), client_id=client_id, scopes=scopes,
            expires_at=now + ACCESS_TTL, resource=resource, subject="owner",
        )
        refresh = RefreshToken(
            token=secrets.token_urlsafe(32), client_id=client_id, scopes=scopes,
            expires_at=now + REFRESH_TTL, resource=resource, subject="owner",
        )
        self.state.oauth_put("access", access.token, {**access.model_dump(mode="json"), "refresh": refresh.token}, access.expires_at)
        self.state.oauth_put("refresh", refresh.token, {**refresh.model_dump(mode="json"), "access": access.token}, refresh.expires_at)
        return OAuthToken(
            access_token=access.token, token_type="Bearer", expires_in=ACCESS_TTL,
            refresh_token=refresh.token, scope=" ".join(scopes),
        )

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        if not self.state.oauth_get("code", authorization_code.code):
            raise TokenError("invalid_grant", "authorization code already used")
        self.state.oauth_delete("code", authorization_code.code)
        assert client.client_id
        return self._issue(client.client_id, authorization_code.scopes, authorization_code.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        data = self.state.oauth_get("refresh", refresh_token)
        if not data or data["client_id"] != client.client_id:
            return None
        return RefreshToken.model_validate({k: v for k, v in data.items() if k != "access"})

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        data = self.state.oauth_get("refresh", refresh_token.token)
        if data:  # rotate: the old pair stops working
            self.state.oauth_delete("access", data.get("access", ""))
        self.state.oauth_delete("refresh", refresh_token.token)
        assert client.client_id
        return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        data = self.state.oauth_get("access", token)
        if not data:
            return None
        return AccessToken.model_validate({k: v for k, v in data.items() if k != "refresh"})

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            data = self.state.oauth_get("access", token.token) or {}
            self.state.oauth_delete("access", token.token)
            self.state.oauth_delete("refresh", data.get("refresh", ""))
        else:
            data = self.state.oauth_get("refresh", token.token) or {}
            self.state.oauth_delete("refresh", token.token)
            self.state.oauth_delete("access", data.get("access", ""))

    async def exchange_identity_assertion(self, client: Any, params: Any) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "not supported")


def _page(body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Wardrobe</title>
<style>
:root {{ color-scheme: light dark; --bg:#faf8f5; --fg:#221f1c; --muted:#786f69; --line:#e2ddd6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#191715; --fg:#f2eee9; --muted:#a59d95; --line:#3a3530; }} }}
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--fg);
  font:17px/1.45 -apple-system, system-ui, sans-serif; }}
main {{ width:min(360px, calc(100vw - 32px)); }}
h1 {{ font-size:24px; margin:0 0 6px; }} p {{ color:var(--muted); margin:0 0 20px; }}
input {{ width:100%; box-sizing:border-box; font:inherit; padding:14px; border-radius:12px; border:1px solid var(--line);
  background:transparent; color:inherit; margin-bottom:12px; }}
button {{ width:100%; font:inherit; font-weight:600; padding:14px; border:0; border-radius:12px; background:var(--fg); color:var(--bg); }}
.err {{ color:#c0392b; }}
</style></head><body><main>{body}</main></body></html>"""


def _login_form(request_id: str, client_name: str, error: bool = False) -> str:
    msg = '<p class="err">Wrong passphrase.</p>' if error else ""
    return _page(
        f"""<h1>Wardrobe</h1><p>{html.escape(client_name)} wants to use your wardrobe.</p>{msg}
<form method="post" action="/login"><input type="hidden" name="req" value="{html.escape(request_id)}">
<input type="password" name="passphrase" placeholder="Passphrase" autocomplete="current-password" autofocus required>
<button type="submit">Allow</button></form>"""
    )
