#!/usr/bin/env python3
"""
Refresh the Monarch Money session token and push it to Azure Table Storage.

Run this script locally (on your Mac) whenever the Monarch token expires.
It uses your saved keychain session — no password re-entry needed if still valid.
If the keychain session is expired, it falls back to interactive login.

Usage:
    cd /Users/mansualu/Desktop/monarch-mcp-server
    python push_monarch_token.py
"""

import asyncio
import os
import sys
import getpass
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from monarchmoney import MonarchMoney, RequireMFAException
from monarch_mcp_server.secure_session import secure_session

AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
MONARCH_SESSION_TABLE = "monarchsession"


def push_to_table_storage(token: str) -> bool:
    """Push the token to Azure Table Storage for the cloud MCP server to use."""
    if not AZURE_STORAGE_CONNECTION_STRING:
        print("❌ AZURE_STORAGE_CONNECTION_STRING not set — cannot push to Azure Table Storage")
        print("   Set it in your shell: export AZURE_STORAGE_CONNECTION_STRING='...'")
        return False
    try:
        from azure.data.tables import TableServiceClient
        service = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        try:
            service.create_table(MONARCH_SESSION_TABLE)
        except Exception:
            pass  # already exists
        table = service.get_table_client(MONARCH_SESSION_TABLE)
        table.upsert_entity({
            "PartitionKey": "token",
            "RowKey": "current",
            "token": token,
        })
        print("✅ Token pushed to Azure Table Storage — MCP server will use it on next call")
        return True
    except Exception as e:
        print(f"❌ Failed to push to Azure Table Storage: {e}")
        return False


async def main():
    print("\n🏦 Monarch Money — Token Refresh & Push")
    print("=" * 45)

    # Try keychain session first (fastest, no re-login needed)
    print("\n🔑 Checking saved keychain session...")
    mm = secure_session.get_authenticated_client()

    if mm:
        print("✅ Keychain session found — testing it...")
        try:
            accounts = await mm.get_accounts()
            count = len(accounts.get("accounts", []))
            print(f"✅ Session valid — {count} accounts accessible")
        except Exception as e:
            print(f"⚠️  Keychain session expired: {e}")
            mm = None

    # If keychain session is expired or missing, do interactive login
    if not mm:
        print("\n🔐 Keychain session invalid — falling back to interactive login...")
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ")

        mm = MonarchMoney()
        try:
            await mm.login(email, password, use_saved_session=False, save_session=True)
            print("✅ Login successful")
        except RequireMFAException:
            code = input("2FA Code: ").strip()
            await mm.multi_factor_authenticate(email, password, code)
            mm.save_session()
            print("✅ MFA login successful")

        # Update keychain too
        secure_session.save_authenticated_session(mm)
        print("✅ Keychain updated")

    # Push to Azure Table Storage
    print("\n☁️  Pushing token to Azure Table Storage...")
    if push_to_table_storage(mm.token):
        print("\n🎉 Done! The Morning Brief will use this token automatically.")
    else:
        print("\n💡 Tip: Set AZURE_STORAGE_CONNECTION_STRING in your environment and re-run.")


if __name__ == "__main__":
    asyncio.run(main())
