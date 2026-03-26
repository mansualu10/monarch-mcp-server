"""
Remote MCP Server with OAuth 2.0 authentication for Azure deployment.
Wraps the MCP SSE transport with OAuth endpoints for Claude.ai integration.
Supports OAuth 2.1 with PKCE and Dynamic Client Registration (RFC 7591).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
from typing import Optional

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP
from monarchmoney import MonarchMoney

from monarch_mcp_server.cloud_session import cloud_session
from monarch_mcp_server.token_store import create_token_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Configuration from environment -----
AZURE_AD_TENANT_ID = os.environ.get("AZURE_AD_TENANT_ID", "")
AZURE_AD_CLIENT_ID = os.environ.get("AZURE_AD_CLIENT_ID", "")
AZURE_AD_CLIENT_SECRET = os.environ.get("AZURE_AD_CLIENT_SECRET", "")
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
OAUTH_SECRET_KEY = os.environ.get("OAUTH_SECRET_KEY", secrets.token_hex(32))

ACCESS_TOKEN_TTL = int(os.environ.get("ACCESS_TOKEN_TTL", 60 * 60 * 24 * 30))  # 30 days default
REFRESH_TOKEN_TTL = int(os.environ.get("REFRESH_TOKEN_TTL", 60 * 60 * 24 * 365))  # 1 year default

# Persistent token store (Azure Table Storage if configured, else in-memory)
token_store = create_token_store()

# ----- MCP Server Setup -----
mcp = FastMCP("Monarch Money MCP Server")

def run_async_in_thread(coro):
    """Run async coroutine in a thread-safe way."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(_run)
        return future.result()


async def get_monarch_client() -> MonarchMoney:
    """Get authenticated MonarchMoney client from environment token."""
    client = cloud_session.get_authenticated_client()
    if client is not None:
        return client
    raise RuntimeError(
        "MONARCH_TOKEN environment variable not set. "
        "Run login_setup.py locally to get your token, then set it as a secret."
    )


# ----- MCP Tools (same as local server) -----

@mcp.tool()
def setup_authentication() -> str:
    """Get instructions for setting up secure authentication with Monarch Money."""
    return "This is a remote MCP server. Authentication is managed via environment variables."


@mcp.tool()
def check_auth_status() -> str:
    """Check if already authenticated with Monarch Money."""
    try:
        token = cloud_session.load_token()
        if token:
            return "Authenticated: MONARCH_TOKEN is set. Try get_accounts to verify."
        return "Not authenticated. MONARCH_TOKEN environment variable is not set."
    except Exception as e:
        return f"Error checking auth status: {str(e)}"


@mcp.tool()
def get_accounts() -> str:
    """Get all financial accounts from Monarch Money."""
    try:
        async def _get():
            client = await get_monarch_client()
            return await client.get_accounts()

        accounts = run_async_in_thread(_get())
        account_list = []
        for account in accounts.get("accounts", []):
            account_list.append({
                "id": account.get("id"),
                "name": account.get("displayName") or account.get("name"),
                "type": (account.get("type") or {}).get("name"),
                "balance": account.get("currentBalance"),
                "institution": (account.get("institution") or {}).get("name"),
                "is_active": account.get("isActive") if "isActive" in account else not account.get("deactivatedAt"),
            })
        return json.dumps(account_list, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get accounts: {e}")
        return f"Error getting accounts: {str(e)}"


@mcp.tool()
def get_transactions(
    limit: int = 100,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[str] = None,
) -> str:
    """Get transactions from Monarch Money."""
    try:
        async def _get():
            client = await get_monarch_client()
            filters = {}
            if start_date:
                filters["start_date"] = start_date
            if end_date:
                filters["end_date"] = end_date
            if account_id:
                filters["account_id"] = account_id
            return await client.get_transactions(limit=limit, offset=offset, **filters)

        transactions = run_async_in_thread(_get())
        transaction_list = []
        for txn in transactions.get("allTransactions", {}).get("results", []):
            transaction_list.append({
                "id": txn.get("id"),
                "date": txn.get("date"),
                "amount": txn.get("amount"),
                "description": txn.get("description"),
                "category": txn.get("category", {}).get("name") if txn.get("category") else None,
                "account": txn.get("account", {}).get("displayName"),
                "merchant": txn.get("merchant", {}).get("name") if txn.get("merchant") else None,
                "is_pending": txn.get("isPending", False),
            })
        return json.dumps(transaction_list, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get transactions: {e}")
        return f"Error getting transactions: {str(e)}"


@mcp.tool()
def get_budgets() -> str:
    """Get budget information from Monarch Money."""
    try:
        async def _get():
            client = await get_monarch_client()
            return await client.get_budgets()

        budgets = run_async_in_thread(_get())
        budget_list = []
        for budget in budgets.get("budgets", []):
            budget_list.append({
                "id": budget.get("id"),
                "name": budget.get("name"),
                "amount": budget.get("amount"),
                "spent": budget.get("spent"),
                "remaining": budget.get("remaining"),
                "category": budget.get("category", {}).get("name"),
                "period": budget.get("period"),
            })
        return json.dumps(budget_list, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get budgets: {e}")
        return f"Error getting budgets: {str(e)}"


@mcp.tool()
def get_cashflow(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """Get cashflow analysis from Monarch Money."""
    try:
        async def _get():
            client = await get_monarch_client()
            filters = {}
            if start_date:
                filters["start_date"] = start_date
            if end_date:
                filters["end_date"] = end_date
            return await client.get_cashflow(**filters)

        cashflow = run_async_in_thread(_get())
        return json.dumps(cashflow, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get cashflow: {e}")
        return f"Error getting cashflow: {str(e)}"


@mcp.tool()
def get_account_holdings(account_id: str) -> str:
    """Get investment holdings for a specific account."""
    try:
        async def _get():
            client = await get_monarch_client()
            return await client.get_account_holdings(account_id)

        holdings = run_async_in_thread(_get())
        return json.dumps(holdings, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get account holdings: {e}")
        return f"Error getting account holdings: {str(e)}"


@mcp.tool()
def refresh_accounts() -> str:
    """Request account data refresh from financial institutions."""
    try:
        async def _get():
            client = await get_monarch_client()
            return await client.request_accounts_refresh()

        result = run_async_in_thread(_get())
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to refresh accounts: {e}")
        return f"Error refreshing accounts: {str(e)}"


# ----- OAuth 2.0 Endpoints -----

def _generate_code() -> str:
    return secrets.token_urlsafe(32)


def _generate_token() -> str:
    return secrets.token_urlsafe(48)


def _generate_client_id() -> str:
    return secrets.token_urlsafe(24)


def _generate_client_secret() -> str:
    return secrets.token_urlsafe(32)


def _verify_code_challenge(verifier: str, challenge: str, method: str = "S256") -> bool:
    """Verify PKCE code challenge."""
    if method == "S256":
        computed = hashlib.sha256(verifier.encode("ascii")).digest()
        computed_challenge = base64.urlsafe_b64encode(computed).rstrip(b"=").decode("ascii")
        return hmac.compare_digest(computed_challenge, challenge)
    elif method == "plain":
        return hmac.compare_digest(verifier, challenge)
    return False


def _generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def _cleanup_expired():
    """Remove expired entries from the token store."""
    token_store.cleanup_expired()


async def oauth_metadata(request: Request) -> JSONResponse:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    return JSONResponse({
        "issuer": SERVER_URL,
        "authorization_endpoint": f"{SERVER_URL}/oauth/authorize",
        "token_endpoint": f"{SERVER_URL}/oauth/token",
        "registration_endpoint": f"{SERVER_URL}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
    })


async def oauth_protected_resource(request: Request) -> JSONResponse:
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return JSONResponse({
        "resource": SERVER_URL,
        "authorization_servers": [SERVER_URL],
        "bearer_methods_supported": ["header"],
    })


async def oauth_register(request: Request) -> JSONResponse:
    """OAuth 2.0 Dynamic Client Registration (RFC 7591)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    client_id = _generate_client_id()
    client_secret = _generate_client_secret()
    redirect_uris = body.get("redirect_uris", [])
    client_name = body.get("client_name", "Unknown Client")

    registered_clients_data = {
        "client_secret": client_secret,
        "redirect_uris": redirect_uris,
        "client_name": client_name,
    }
    token_store.set_registered_client(client_id, registered_clients_data)

    logger.info(f"Registered OAuth client: {client_name} ({client_id})")

    return JSONResponse({
        "client_id": client_id,
        "client_secret": client_secret,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }, status_code=201)


async def oauth_authorize(request: Request) -> Response:
    """OAuth 2.0 Authorization endpoint. Redirects to Azure AD for login."""
    _cleanup_expired()

    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")

    if not redirect_uri:
        return JSONResponse({"error": "invalid_request", "error_description": "redirect_uri required"}, status_code=400)

    # Store OAuth state for when Azure AD calls back
    internal_state = secrets.token_urlsafe(32)
    token_store.set_oauth_state(internal_state, {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires": time.time() + 600,
    })

    if AZURE_AD_TENANT_ID and AZURE_AD_CLIENT_ID:
        azure_auth_url = (
            f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/oauth2/v2.0/authorize?"
            + urllib.parse.urlencode({
                "client_id": AZURE_AD_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": f"{SERVER_URL}/oauth/callback",
                "scope": "openid profile email",
                "state": internal_state,
                "response_mode": "query",
            })
        )
        return RedirectResponse(azure_auth_url)
    else:
        # No Azure AD configured — auto-approve for single-user setup
        code = _generate_code()
        token_store.set_auth_code(code, {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "expires": time.time() + 300,
        })
        redirect = f"{redirect_uri}?code={code}"
        if state:
            redirect += f"&state={state}"
        return RedirectResponse(redirect)


async def oauth_callback(request: Request) -> Response:
    """Callback from Azure AD after user authenticates."""
    params = dict(request.query_params)
    internal_state = params.get("state", "")
    error = params.get("error", "")

    if error:
        return JSONResponse({"error": "access_denied", "error_description": params.get("error_description", error)}, status_code=403)

    stored = token_store.pop_oauth_state(internal_state)
    if not stored:
        return JSONResponse({"error": "invalid_state", "error_description": "Unknown or expired state"}, status_code=400)

    # Azure AD authenticated the user — issue our own auth code to Claude
    code = _generate_code()
    token_store.set_auth_code(code, {
        "client_id": stored["client_id"],
        "redirect_uri": stored["redirect_uri"],
        "code_challenge": stored["code_challenge"],
        "code_challenge_method": stored["code_challenge_method"],
        "expires": time.time() + 300,
    })

    redirect = f"{stored['redirect_uri']}?code={code}"
    if stored.get("state"):
        redirect += f"&state={stored['state']}"
    return RedirectResponse(redirect)


async def oauth_token(request: Request) -> JSONResponse:
    """OAuth 2.0 Token endpoint. Supports authorization_code and refresh_token grants."""
    _cleanup_expired()

    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form = dict(await request.form())
    elif "application/json" in content_type:
        try:
            form = await request.json()
        except Exception:
            form = {}
    else:
        # Try form first, fall back to JSON
        try:
            form = dict(await request.form())
        except Exception:
            try:
                form = await request.json()
            except Exception:
                form = dict(request.query_params)

    grant_type = form.get("grant_type", "")

    if grant_type == "refresh_token":
        rt = form.get("refresh_token", "")
        stored_rt = token_store.pop_refresh_token(rt)
        if not stored_rt:
            return JSONResponse({"error": "invalid_grant", "error_description": "Invalid or expired refresh token"}, status_code=400)

        # Issue new access token (and rotate the refresh token)
        new_access = _generate_token()
        new_refresh = _generate_refresh_token()
        token_store.set_access_token(new_access, {
            "client_id": stored_rt["client_id"],
            "expires": time.time() + ACCESS_TOKEN_TTL,
        })
        token_store.set_refresh_token(new_refresh, {
            "client_id": stored_rt["client_id"],
            "expires": time.time() + REFRESH_TOKEN_TTL,
        })

        logger.info(f"Refreshed access token for client {stored_rt['client_id']}")
        return JSONResponse({
            "access_token": new_access,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL,
            "refresh_token": new_refresh,
        })

    if grant_type != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    code = form.get("code", "")
    code_verifier = form.get("code_verifier", "")

    stored_code = token_store.pop_auth_code(code)
    if not stored_code:
        return JSONResponse({"error": "invalid_grant", "error_description": "Invalid or expired code"}, status_code=400)

    if stored_code["expires"] < time.time():
        return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"}, status_code=400)

    # Verify PKCE if challenge was provided
    if stored_code.get("code_challenge") and code_verifier:
        if not _verify_code_challenge(code_verifier, stored_code["code_challenge"], stored_code.get("code_challenge_method", "S256")):
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

    # Issue access token and refresh token
    token = _generate_token()
    rt = _generate_refresh_token()
    token_store.set_access_token(token, {
        "client_id": stored_code["client_id"],
        "expires": time.time() + ACCESS_TOKEN_TTL,
    })
    token_store.set_refresh_token(rt, {
        "client_id": stored_code["client_id"],
        "expires": time.time() + REFRESH_TOKEN_TTL,
    })

    return JSONResponse({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL,
        "refresh_token": rt,
    })


async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "service": "monarch-mcp-server"})


def validate_bearer_token(request: Request) -> bool:
    """Validate Bearer token from request."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]
    stored = token_store.get_access_token(token)
    return stored is not None


# ----- Streamable HTTP Transport with Auth -----

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

session_manager = StreamableHTTPSessionManager(
    app=mcp._mcp_server,
    stateless=True,
    json_response=False,
)


from starlette.types import Receive, Scope, Send


async def handle_mcp_request(scope: Scope, receive: Receive, send: Send) -> None:
    """ASGI app that handles MCP requests with auth check."""
    request = Request(scope, receive, send)

    if not validate_bearer_token(request):
        response = JSONResponse({"error": "unauthorized"}, status_code=401)
        await response(scope, receive, send)
        return

    await session_manager.handle_request(scope, receive, send)


# ----- App Assembly -----

@asynccontextmanager
async def lifespan(app_instance: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        yield


routes = [
    Route("/health", health_check),
    Route("/.well-known/oauth-authorization-server", oauth_metadata),
    Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
    Route("/oauth/register", oauth_register, methods=["POST"]),
    Route("/oauth/authorize", oauth_authorize),
    Route("/oauth/callback", oauth_callback),
    Route("/oauth/token", oauth_token, methods=["POST"]),
    Mount("/mcp", app=handle_mcp_request),
    Mount("/", app=handle_mcp_request),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["https://claude.ai", "https://www.claude.ai"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        ),
    ],
)


def main():
    """Main entry point for the remote server."""
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting Monarch Money Remote MCP Server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
