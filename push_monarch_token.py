#!/usr/bin/env python3
"""Refresh the Monarch Money session token and push it to Azure Table Storage.

Usage:
    AZURE_STORAGE_CONNECTION_STRING='...' python push_monarch_token.py
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from monarchmoney import MonarchMoney, RequireMFAException
from monarch_mcp_server.secure_session import secure_session

AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
MONARCH_SESSION_TABLE = "monarchsession"


def push_to_table_storage(token: str) -> bool:
    """Push the token to Azure Table Storage for the cloud MCP server to use."""
    if not AZURE_STORAGE_CONNECTION_STRING:
        print("❌ AZURE_STORAGE_CONNECTION_STRING not set")
        return False
    try:
        from azure.data.tables import TableServiceClient
        service = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        try:
            service.create_table(MONARCH_SESSION_TABLE)
        except Exception:
            pass
        table = service.get_table_client(MONARCH_SESSION_TABLE)
        table.upsert_entity({
            "PartitionKey": "token",
            "RowKey": "current",
            "token": token,
        })
        print("✅ Token pushed to Azure Table Storage")
        return True
    except Exception as e:
        print(f"❌ Failed to push to Azure Table Storage: {e}")
        return False


async def main():
    print("\n🏦 Monarch Money — Token Refresh & Push")
    print("=" * 40)

    mm = secure_session.get_authenticated_client()

    if mm:
        try:
            accounts = await mm.get_accounts()
            count = len(accounts.get("accounts", []))
            print(f"✅ Keychain session valid — {count} accounts")
        except Exception:
            mm = None

    if not mm:
        print("🔐 Keychain session invalid — logging in...")
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

        secure_session.save_authenticated_session(mm)

    push_to_table_storage(mm.token)


if __name__ == "__main__":
    asyncio.run(main())
