# Auth: single-user OAuth

Status: complete

## Purpose

Lets ChatGPT/Claude connect to the public `/mcp` endpoint safely. They register
themselves (dynamic client registration), send the user to a one-page login,
the user types the passphrase once, and the client receives tokens.

## Public API

- `PassphraseOAuthProvider(state, public_url, passphrase)` implements the MCP
  SDK's `OAuthAuthorizationServerProvider`:
  - `get_client`, `register_client`
  - `authorize`: stores a pending request and returns `/login?req=…`
  - `login_page(request)`: the `GET` form and `POST` check; on success it
    issues an authorization code and redirects to the client
  - `load_authorization_code`, `exchange_authorization_code` (single use)
  - `load_refresh_token`, `exchange_refresh_token` (**rotates** the pair)
  - `load_access_token`, `revoke_token`
  - `exchange_identity_assertion`: unsupported
- `SCOPE = "wardrobe"`; TTLs: access 7 days, refresh 365 days, code 5 min,
  pending login 15 min.

## Implementation files

- `src/wardrobe/auth.py`: the provider plus the inline login page HTML.
- Wired in `src/wardrobe/server.py` (`build_mcp`: `AuthSettings`,
  `/login` route).

## Dependencies

- Allowed: `state` (all OAuth rows), `mcp.server.auth`, `mcp.shared.auth`,
  `starlette` (login request/response).
- Forbidden: `catalog`, `server`.

## Constraints

- PKCE, redirect URI checks and code expiry are enforced by the SDK's handlers.
  Don't re-implement them.
- Passphrase comparison uses `hmac.compare_digest`. After 10 failures in
  15 minutes, login is blocked (in memory, resets on restart).
- The login page sends `X-Frame-Options: DENY`, `Cache-Control: no-store` and
  `Referrer-Policy: no-referrer`.
- `validate_token_resource=False`: clients may omit the RFC 8707 resource.
- Issuer = `WARDROBE_PUBLIC_URL` **exactly** (https, no trailing slash).
  Otherwise clients reject the metadata.

## Tests

- `tests/test_http.py::test_oauth_and_mcp_over_http`: the full flow over real
  HTTP (401 + resource metadata, registration, authorize → login → wrong and
  right passphrase, code → token, MCP calls with the token, refresh rotation,
  old token rejected).

## Non-goals

- No multiple users, no external identity provider, no scopes beyond
  `wardrobe`.
