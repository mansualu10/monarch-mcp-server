import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from monarchmoney import MonarchMoney  # provided by monarchmoneycommunity
from monarch_mcp_server.investments import build_investment_exec_view
from monarch_mcp_server.secure_session import secure_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Monarch Money MCP Server")


def run_async(coro):
    """Run async function in a new thread with its own event loop."""

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
    """Get or create MonarchMoney client instance using secure keyring storage only."""
    client = secure_session.get_authenticated_client()

    if client is not None:
        logger.info("Using authenticated client from secure keyring storage")
        return client

    raise RuntimeError(
        "Authentication needed! Run: python login_setup.py\n"
        "Credentials are stored in the macOS Keychain — never in env vars or files."
    )


@mcp.tool()
def setup_authentication() -> str:
    """Get instructions for setting up secure authentication with Monarch Money."""
    return """🔐 Monarch Money - One-Time Setup

1️⃣ Open Terminal and run:
   python login_setup.py

2️⃣ Enter your Monarch Money credentials when prompted
   • Email and password
   • 2FA code if you have MFA enabled

3️⃣ Session will be saved automatically and last for weeks

4️⃣ Start using Monarch tools in Claude Desktop:
   • get_accounts - View all accounts
   • get_transactions - Recent transactions
   • get_budgets - Budget information

✅ Session persists across Claude restarts
✅ No need to re-authenticate frequently
✅ All credentials stay secure in terminal"""


@mcp.tool()
def check_auth_status() -> str:
    """Check if already authenticated with Monarch Money."""
    try:
        token = secure_session.load_token()
        if token:
            return "Authenticated: token found in secure keyring storage. Try get_accounts to test."
        else:
            return "Not authenticated. Run login_setup.py to set up credentials in the macOS Keychain."
    except Exception as e:
        return f"Error checking auth status: {str(e)}"

@mcp.tool()
def get_accounts() -> str:
    """Get all financial accounts from Monarch Money."""
    try:

        async def _get_accounts():
            client = await get_monarch_client()
            return await client.get_accounts()

        accounts = run_async(_get_accounts())

        # Format accounts for display
        account_list = []
        for account in accounts.get("accounts", []):
            account_info = {
                "id": account.get("id"),
                "name": account.get("displayName") or account.get("name"),
                "type": (account.get("type") or {}).get("name"),
                "balance": account.get("currentBalance"),
                "institution": (account.get("institution") or {}).get("name"),
                "is_active": account.get("isActive")
                if "isActive" in account
                else not account.get("deactivatedAt"),
            }
            account_list.append(account_info)

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
    """
    Get transactions from Monarch Money.

    Args:
        limit: Number of transactions to retrieve (default: 100)
        offset: Number of transactions to skip (default: 0)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        account_id: Specific account ID to filter by
    """
    try:

        async def _get_transactions():
            client = await get_monarch_client()

            # Build filters
            filters = {}
            if start_date:
                filters["start_date"] = start_date
            if end_date:
                filters["end_date"] = end_date
            if account_id:
                filters["account_id"] = account_id

            return await client.get_transactions(limit=limit, offset=offset, **filters)

        transactions = run_async(_get_transactions())

        # Format transactions for display
        transaction_list = []
        for txn in transactions.get("allTransactions", {}).get("results", []):
            transaction_info = {
                "id": txn.get("id"),
                "date": txn.get("date"),
                "amount": txn.get("amount"),
                "description": txn.get("description"),
                "category": txn.get("category", {}).get("name")
                if txn.get("category")
                else None,
                "account": txn.get("account", {}).get("displayName"),
                "merchant": txn.get("merchant", {}).get("name")
                if txn.get("merchant")
                else None,
                "is_pending": txn.get("isPending", False),
            }
            transaction_list.append(transaction_info)

        return json.dumps(transaction_list, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get transactions: {e}")
        return f"Error getting transactions: {str(e)}"


@mcp.tool()
def get_budgets() -> str:
    """Get budget information from Monarch Money."""
    try:

        async def _get_budgets():
            client = await get_monarch_client()
            return await client.get_budgets()

        budgets = run_async(_get_budgets())

        # Format budgets for display
        budget_list = []
        for budget in budgets.get("budgets", []):
            budget_info = {
                "id": budget.get("id"),
                "name": budget.get("name"),
                "amount": budget.get("amount"),
                "spent": budget.get("spent"),
                "remaining": budget.get("remaining"),
                "category": budget.get("category", {}).get("name"),
                "period": budget.get("period"),
            }
            budget_list.append(budget_info)

        return json.dumps(budget_list, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get budgets: {e}")
        return f"Error getting budgets: {str(e)}"


@mcp.tool()
def get_cashflow(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> str:
    """
    Get cashflow analysis from Monarch Money.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    try:

        async def _get_cashflow():
            client = await get_monarch_client()

            filters = {}
            if start_date:
                filters["start_date"] = start_date
            if end_date:
                filters["end_date"] = end_date

            return await client.get_cashflow(**filters)

        cashflow = run_async(_get_cashflow())

        return json.dumps(cashflow, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get cashflow: {e}")
        return f"Error getting cashflow: {str(e)}"


@mcp.tool()
def get_account_holdings(account_id: str) -> str:
    """
    Get investment holdings for a specific account.

    Args:
        account_id: The ID of the investment account
    """
    try:

        async def _get_holdings():
            client = await get_monarch_client()
            return await client.get_account_holdings(account_id)

        holdings = run_async(_get_holdings())

        return json.dumps(holdings, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get account holdings: {e}")
        return f"Error getting account holdings: {str(e)}"


@mcp.tool()
def get_investment_exec_view() -> str:
    """Get an executive investments view with a summary card and rolled-up holdings."""
    try:

        async def _get_exec_view():
            client = await get_monarch_client()
            accounts = await client.get_accounts()
            account_list = []
            investment_ids = []

            for account in accounts.get("accounts", []):
                account_info = {
                    "id": account.get("id"),
                    "name": account.get("displayName") or account.get("name"),
                    "type": (account.get("type") or {}).get("name"),
                    "balance": account.get("currentBalance"),
                    "institution": (account.get("institution") or {}).get("name"),
                    "is_active": account.get("isActive")
                    if "isActive" in account
                    else not account.get("deactivatedAt"),
                }
                account_list.append(account_info)
                if account_info["is_active"] and account_info["type"] == "brokerage":
                    investment_ids.append(account_info["id"])

            holdings_pairs = await asyncio.gather(
                *(client.get_account_holdings(account_id) for account_id in investment_ids)
            )
            holdings_by_account = {
                account_id: json.dumps(payload, default=str)
                for account_id, payload in zip(investment_ids, holdings_pairs, strict=True)
            }
            return build_investment_exec_view(
                json.dumps(account_list, default=str),
                holdings_by_account,
            )

        return run_async(_get_exec_view())
    except Exception as e:
        logger.error(f"Failed to build investment exec view: {e}")
        return f"Error building investment exec view: {str(e)}"

@mcp.tool()
def refresh_accounts() -> str:
    """Request account data refresh from financial institutions."""
    try:

        async def _refresh_accounts():
            client = await get_monarch_client()
            return await client.request_accounts_refresh()

        result = run_async(_refresh_accounts())

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to refresh accounts: {e}")
        return f"Error refreshing accounts: {str(e)}"


def main():
    """Main entry point for the server."""
    logger.info("Starting Monarch Money MCP Server...")
    try:
        mcp.run()
    except Exception as e:
        logger.error(f"Failed to run server: {str(e)}")
        raise


# Export for mcp run
app = mcp

if __name__ == "__main__":
    main()
