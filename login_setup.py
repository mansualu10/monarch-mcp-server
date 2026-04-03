#!/usr/bin/env python3
"""Interactive Monarch Money login with MFA support.
Authenticates and saves a session token to the system keyring for the MCP server.
"""

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from monarchmoney import MonarchMoney, RequireMFAException
from monarch_mcp_server.secure_session import secure_session


async def main():
    print("\n🏦 Monarch Money - Login Setup")
    print("=" * 40)

    mm = MonarchMoney()
    secure_session.delete_token()

    email = input("Email: ")
    password = getpass.getpass("Password: ")

    try:
        await mm.login(email, password, use_saved_session=False, save_session=True)
        print("✅ Login successful!")
    except RequireMFAException:
        mfa_code = input("2FA Code: ")
        await mm.multi_factor_authenticate(email, password, mfa_code)
        mm.save_session()
        print("✅ MFA login successful!")

    # Verify the session works
    accounts = await mm.get_accounts()
    count = len(accounts.get("accounts", []))
    print(f"✅ Connected — {count} accounts found")

    secure_session.save_authenticated_session(mm)
    print("✅ Session saved to system keyring")
    print("\n🎉 Setup complete! Restart Claude Desktop to start using Monarch tools.")


if __name__ == "__main__":
    asyncio.run(main())