# Auth: single-user OAuth

Status: complete

## Purpose

Lets ChatGPT/Claude connect to the public `/mcp` endpoint safely. They identify
themselves in one of two ways:

- **CIMD**: the `client_id` is an https URL to the client's published metadata
  document. This is Claude's recommended default ("use Claude's published
  identity").
- **Dynamic client registration** (`/register`).

Then they send the user to a one-page login, the user types the passphrase
once, and the client receives tokens.

## Public API

- `PassphraseOAuthProvider(state, public_url, passphrase)` implements the MCP
  SDK's `OAuthAuthorizationServerProvider`:
  - `get_client`: stored client, or for an `https://` client_id, fetch and
    validate its metadata document (CIMD) and cache it for 1 h
  - `register_client` (DCR)
  - `authorize`: stores a pending request and returns `/login?req=…`
  - `login_page(request)`: the `GET` form and `POST` check; on success it
    issues an authorization code and redirects to the client
  - `load_authorization_code`, `exchange_authorization_code` (single use)
  - `load_refresh_token`, `exchange_refresh_token` (**rotates** the pair)
  - `load_access_token`, `revoke_token`
  - `exchange_identity_assertion`: unsupported
- `is_trusted_cimd_url(url)`, `fetch_json(url)` (patched in tests),
  `CIMD_TRUSTED_DOMAINS`
- `SCOPE = "wardrobe"`; TTLs: access 7 days, refresh 365 days, code 5 min,
  pending login 15 min.

## Implementation files

- `src/wardrobe/auth.py`: the provider plus the inline login page HTML.
- Wired in `src/wardrobe/server.py` (`build_mcp`: `AuthSettings`,
  `/login` route; `_advertise_client_metadata_documents` replaces the SDK's
  metadata route to add `client_id_metadata_document_supported: true` and
  the `none` token auth method).

## Dependencies

- Allowed: `state` (all OAuth rows), `mcp.server.auth`, `mcp.shared.auth`,
  `starlette` (login request/response), `httpx` (CIMD fetch only), `pydantic`
  (validation errors).
- Forbidden: `catalog`, `server`.

## Constraints

- PKCE, redirect URI checks and code expiry are enforced by the SDK's handlers.
  Don't re-implement them.
- Passphrase comparison uses `hmac.compare_digest`. After 10 failures in
  15 minutes, login is blocked (in memory, resets on restart).
- The login page sends `X-Frame-Options: DENY`, `Cache-Control: no-store` and
  `Referrer-Policy: no-referrer`.
- CIMD documents are fetched **only** from `CIMD_TRUSTED_DOMAINS`
  (claude.ai, claude.com, anthropic.com, chatgpt.com, openai.com and their
  subdomains). The rules: https on port 443 only, no redirects, ≤ 64 KB, and
  the document's `client_id` must equal its URL. This prevents a stranger
  making the home server fetch arbitrary addresses (SSRF). CIMD clients are
  treated as public clients (`none`): PKCE plus the document's `redirect_uris`
  protect the flow.
- `validate_token_resource=False`: clients may omit the RFC 8707 resource.
- Issuer = `WARDROBE_PUBLIC_URL` **exactly** (https, no trailing slash).
  Otherwise clients reject the metadata.

## Tests

- `tests/test_http.py::test_oauth_and_mcp_over_http`: the full flow over real
  HTTP (401 + resource metadata, registration, authorize → login → wrong and
  right passphrase, code → token, MCP calls with the token, refresh rotation,
  old token rejected).
- `tests/test_http.py::test_client_metadata_document_login`: metadata
  advertises CIMD; an untrusted domain is never fetched; a mismatched document
  is rejected; Claude's CIMD client completes login → token → MCP; the document
  is cached.

## Non-goals

- No multiple users, no external identity provider, no scopes beyond
  `wardrobe`.
- No fetching of client metadata from arbitrary domains. Extend
  `CIMD_TRUSTED_DOMAINS` only for a known AI client.
