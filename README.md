[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/robcerda-monarch-mcp-server-badge.png)](https://mseep.ai/app/robcerda-monarch-mcp-server)

# Monarch Money MCP Server

A Model Context Protocol (MCP) server for integrating with the Monarch Money personal finance platform. This server provides seamless access to your financial accounts, transactions, budgets, and analytics through Claude Desktop.

My MonarchMoney referral: https://www.monarchmoney.com/referral/ufmn0r83yf?r_source=share

**Built with the [MonarchMoney Python library](https://github.com/hammem/monarchmoney) by [@hammem](https://github.com/hammem)** - A fantastic unofficial API for Monarch Money with full MFA support.

<a href="https://glama.ai/mcp/servers/@robcerda/monarch-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@robcerda/monarch-mcp-server/badge" alt="monarch-mcp-server MCP server" />
</a>

## 🚀 Quick Start

### 1. Installation

1. **Clone this repository**:
   ```bash
   git clone https://github.com/robcerda/monarch-mcp-server.git
   cd monarch-mcp-server
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Configure Claude Desktop**:
   Add this to your Claude Desktop configuration file:
   
   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   
   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   
   ```json
   {
     "mcpServers": {
       "Monarch Money": {
         "command": "/opt/homebrew/bin/uv",
         "args": [
           "run",
           "--with",
           "mcp[cli]",
           "--with-editable",
           "/path/to/your/monarch-mcp-server",
           "mcp",
           "run",
           "/path/to/your/monarch-mcp-server/src/monarch_mcp_server/server.py"
         ]
       }
     }
   }
   ```
   
   **Important**: Replace `/path/to/your/monarch-mcp-server` with your actual path!

4. **Restart Claude Desktop**

### 2. One-Time Authentication Setup

**Important**: For security and MFA support, authentication is done outside of Claude Desktop.

Open Terminal and run:
```bash
cd /path/to/your/monarch-mcp-server
python login_setup.py
```

Follow the prompts:
- Enter your Monarch Money email and password
- Provide 2FA code if you have MFA enabled
- Session will be saved automatically

### 3. Start Using in Claude Desktop

Once authenticated, use these tools directly in Claude Desktop:
- `get_accounts` - View all your financial accounts
- `get_transactions` - Recent transactions with filtering
- `get_budgets` - Budget information and spending
- `get_cashflow` - Income/expense analysis

## ✨ Features

### 📊 Account Management
- **Get Accounts**: View all linked financial accounts with balances and institution info
- **Get Account Holdings**: See securities and investments in investment accounts
- **Investment Executive View**: Aggregated portfolio view with live market prices
- **Refresh Accounts**: Request real-time data updates from financial institutions

### 💰 Transaction Access
- **Get Transactions**: Fetch transaction data with filtering by date, account, and pagination

### 📈 Financial Analysis
- **Get Budgets**: Access budget information including spent amounts and remaining balances
- **Get Cashflow**: Analyze financial cashflow over specified date ranges with income/expense breakdowns

### 🔐 Secure Authentication
- **One-Time Setup**: Authenticate once, use for weeks/months
- **MFA Support**: Full support for two-factor authentication
- **Keyring Storage**: Token stored securely in the system keyring (macOS Keychain)
- **Secure**: Credentials never pass through Claude Desktop

## 🛠️ Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `setup_authentication` | Get setup instructions | None |
| `check_auth_status` | Check authentication status | None |
| `get_accounts` | Get all financial accounts | None |
| `get_transactions` | Get transactions with filtering | `limit`, `offset`, `start_date`, `end_date`, `account_id` |
| `get_budgets` | Get budget information | None |
| `get_cashflow` | Get cashflow analysis | `start_date`, `end_date` |
| `get_account_holdings` | Get investment holdings | `account_id` |
| `get_investment_exec_view` | Aggregated portfolio summary | None |
| `refresh_accounts` | Request account data refresh | None |

## 📝 Usage Examples

### View Your Accounts
```
Use get_accounts to show me all my financial accounts
```

### Get Recent Transactions
```
Show me my last 50 transactions using get_transactions with limit 50
```

### Check Spending vs Budget
```
Use get_budgets to show my current budget status
```

### Analyze Cash Flow
```
Get my cashflow for the last 3 months using get_cashflow
```

## 📅 Date Formats

- All dates should be in `YYYY-MM-DD` format (e.g., "2024-01-15")
- Transaction amounts: **positive** for income, **negative** for expenses

## 🔧 Troubleshooting

### Authentication Issues
If you see "Authentication needed" errors:
1. Run the setup command: `cd /path/to/your/monarch-mcp-server && python login_setup.py`
2. Restart Claude Desktop
3. Try using a tool like `get_accounts`

### Session Expired
Sessions last for weeks, but if expired:
1. Run the same setup command again
2. Enter your credentials and 2FA code
3. Session will be refreshed automatically

### Common Error Messages
- **"No valid session found"**: Run `login_setup.py` 
- **"Invalid account ID"**: Use `get_accounts` to see valid account IDs
- **"Date format error"**: Use YYYY-MM-DD format for dates

## 🏗️ Technical Details

### Project Structure
```
monarch-mcp-server/
├── src/monarch_mcp_server/
│   ├── __init__.py
│   ├── server.py          # Local MCP server (keyring auth)
│   ├── remote_server.py   # Cloud MCP server (Azure + OAuth)
│   ├── secure_session.py  # Keyring-based token storage
│   ├── cloud_session.py   # Azure Table Storage session
│   ├── investments.py     # Investment aggregation helpers
│   └── token_store.py     # OAuth token persistence
├── scripts/
│   ├── daily_snapshot.py  # Daily investment email report
│   └── run_daily_snapshot.sh
├── tests/
│   └── test_investments.py
├── login_setup.py         # One-time authentication setup
├── push_monarch_token.py  # Push token to Azure for cloud server
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Session Management
- Token stored securely in the system keyring (macOS Keychain)
- Automatic session loading on server start
- Sessions persist across Claude Desktop restarts

### Security Features
- Credentials never transmitted through Claude Desktop
- MFA/2FA fully supported
- Token stored in system keyring, not in files
- Authentication handled in secure terminal environment

## 🙏 Acknowledgments

This MCP server is built on top of the excellent [MonarchMoney Python library](https://github.com/hammem/monarchmoney) created by [@hammem](https://github.com/hammem). Their library provides the robust foundation that makes this integration possible, including:

- Secure authentication with MFA support
- Comprehensive API coverage for Monarch Money
- Session management and persistence
- Well-documented and maintained codebase

Thank you to [@hammem](https://github.com/hammem) for creating and maintaining this essential library!

## 📄 License

MIT License

## 🆘 Support

For issues:
1. Check authentication with `check_auth_status`
2. Run the setup command again: `cd /path/to/your/monarch-mcp-server && python login_setup.py`
3. Check error logs for detailed messages
4. Ensure Monarch Money service is accessible

## 🔄 Updates

To update the server:
1. Pull latest changes from repository
2. Restart Claude Desktop
3. Re-run authentication if needed: `python login_setup.py`