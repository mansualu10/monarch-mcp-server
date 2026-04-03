#!/usr/bin/env python3
"""Daily investment snapshot — prints holdings table and optionally emails it.

Usage (print only):
    ALPHA_VANTAGE_API_KEY=<key> python3 scripts/daily_snapshot.py

Usage (send email):
    ALPHA_VANTAGE_API_KEY=<key> \\
    SNAPSHOT_EMAIL_TO=you@gmail.com \\
    SNAPSHOT_EMAIL_FROM=you@gmail.com \\
    SNAPSHOT_GMAIL_APP_PASSWORD=<app-password> \\
    python3 scripts/daily_snapshot.py

Requires the package to be installed in the active venv:
    pip install -e .
"""

from __future__ import annotations

import asyncio
import email.mime.multipart
import email.mime.text
import json
import os
import smtplib
import sys
from datetime import date
from pathlib import Path

# Allow running from the repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from monarchmoney import MonarchMoney  # provided by monarchmoneycommunity
from monarch_mcp_server.secure_session import secure_session
from monarch_mcp_server.investments import build_investment_exec_view


async def _fetch_data() -> str:
    token = secure_session.load_token()
    if not token:
        print("ERROR: Not authenticated. Run python login_setup.py first.", file=sys.stderr)
        sys.exit(1)

    client = MonarchMoney(token=token)

    accounts_raw = await client.get_accounts()
    account_list = []
    investment_ids = []

    for account in accounts_raw.get("accounts", []):
        info = {
            "id": account.get("id"),
            "name": account.get("displayName") or account.get("name"),
            "type": (account.get("type") or {}).get("name"),
            "balance": account.get("currentBalance"),
            "institution": (account.get("institution") or {}).get("name"),
            "is_active": account.get("isActive")
            if "isActive" in account
            else not account.get("deactivatedAt"),
        }
        account_list.append(info)
        if info["is_active"] and info["type"] == "brokerage":
            investment_ids.append(info["id"])

    if not investment_ids:
        print("No active brokerage accounts found.", file=sys.stderr)
        sys.exit(1)

    holdings_pairs = await asyncio.gather(
        *(client.get_account_holdings(aid) for aid in investment_ids)
    )
    holdings_by_account = {
        aid: json.dumps(payload, default=str)
        for aid, payload in zip(investment_ids, holdings_pairs)
    }

    return build_investment_exec_view(
        json.dumps(account_list, default=str),
        holdings_by_account,
    )


def _render_table(view_json: str) -> str:
    data = json.loads(view_json)
    rows = data["rows"]
    today = date.today().strftime("%B %d, %Y")

    def accounts_str(r: dict) -> str:
        return ", ".join(r.get("accounts") or [])

    col_ticker   = max(6,  max((len(r["symbol"])                       for r in rows), default=0))
    col_name     = max(4,  max((len(r["name"])                         for r in rows), default=0))
    col_shares   = max(9,  max((len(r["quantity_display"] or "")       for r in rows), default=0))
    col_price    = max(7,  max((len(r["latest_price_display"] or "—")  for r in rows), default=0))
    col_value    = max(11, max((len(r["total_value_display"] or "—")   for r in rows), default=0))
    col_accounts = max(8,  max((len(accounts_str(r))                   for r in rows), default=0))

    def sep() -> str:
        return (
            f"+-{'-' * col_ticker}-+-{'-' * col_name}-+"
            f"-{'-' * col_shares}-+-{'-' * col_price}-+-{'-' * col_value}-+"
            f"-{'-' * col_accounts}-+"
        )

    def row_line(ticker, name, shares, price, value, accounts) -> str:
        return (
            f"| {ticker:<{col_ticker}} | {name:<{col_name}} |"
            f" {shares:>{col_shares}} | {price:>{col_price}} | {value:>{col_value}} |"
            f" {accounts:<{col_accounts}} |"
        )

    lines = [
        f"Daily Investment Snapshot — {today}",
        "",
        sep(),
        row_line("Ticker", "Name", "Shares", "Price", "Total Value", "Accounts"),
        sep(),
    ]

    total = 0.0
    for r in rows:
        price_str = r["latest_price_display"] or "—"
        value_str = r["total_value_display"] or "—"
        shares_str = r["quantity_display"] or "—"
        lines.append(row_line(r["symbol"], r["name"], shares_str, price_str, value_str, accounts_str(r)))
        total += r["total_value"] or 0.0

    total_display = f"${total:,.2f}"
    lines.append(sep())
    lines.append(row_line("", "TOTAL", "", "", total_display, ""))
    lines.append(sep())
    lines.append("")

    card = data["card"]
    lines.append(f"Portfolio total: {card['current_value_display']}")
    meta = data["meta"]
    lines.append(
        f"Accounts: {meta['active_investment_account_count']}  |  "
        f"Holdings: {meta['holding_count']}  |  "
        f"Price source: {', '.join(meta['price_sources'])}"
    )

    return "\n".join(lines)


def _render_html(view_json: str) -> str:
    data = json.loads(view_json)
    rows = data["rows"]
    today = date.today().strftime("%B %d, %Y")
    meta = data["meta"]

    def accounts_str(r: dict) -> str:
        return ", ".join(r.get("accounts") or [])

    tbody_rows = ""
    total = 0.0
    for r in rows:
        price = r["latest_price_display"] or "—"
        value = r["total_value_display"] or "—"
        shares = r["quantity_display"] or "—"
        accts = accounts_str(r)
        tbody_rows += (
            f"<tr>"
            f"<td>{r['symbol']}</td>"
            f"<td>{r['name']}</td>"
            f"<td class='num'>{shares}</td>"
            f"<td class='num'>{price}</td>"
            f"<td class='num'>{value}</td>"
            f"<td>{accts}</td>"
            f"</tr>\n"
        )
        total += r["total_value"] or 0.0

    total_display = f"${total:,.2f}"

    return f"""<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 24px; }}
  .container {{ background: white; border-radius: 8px; padding: 24px; max-width: 1100px; margin: 0 auto; }}
  h2 {{ color: #1a1a1a; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: 13px; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th {{ background: #1a1a1a; color: white; padding: 10px 12px; text-align: left; white-space: nowrap; }}
  th.num {{ text-align: right; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #eee; white-space: nowrap; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .total-row td {{ font-weight: bold; background: #f0f0f0; border-top: 2px solid #1a1a1a; }}
  .footer {{ margin-top: 16px; font-size: 12px; color: #999; }}
</style>
</head>
<body>
<div class="container">
  <h2>Daily Investment Snapshot</h2>
  <div class="subtitle">
    {today} &nbsp;·&nbsp;
    {meta['active_investment_account_count']} accounts &nbsp;·&nbsp;
    {meta['holding_count']} holdings &nbsp;·&nbsp;
    Prices: {', '.join(meta['price_sources'])}
  </div>
  <table>
    <thead>
      <tr>
        <th>Ticker</th><th>Name</th>
        <th class="num">Shares</th><th class="num">Price</th>
        <th class="num">Total Value</th><th>Accounts</th>
      </tr>
    </thead>
    <tbody>
{tbody_rows}      <tr class="total-row">
        <td></td><td>TOTAL</td><td></td><td></td>
        <td class="num">{total_display}</td><td></td>
      </tr>
    </tbody>
  </table>
  <div class="footer">Generated by Monarch MCP · Prices via Alpha Vantage · Cash positions priced at $1.00</div>
</div>
</body>
</html>"""


def _send_email(subject: str, html_body: str, plain_body: str) -> None:
    to_addr   = os.environ["SNAPSHOT_EMAIL_TO"]
    from_addr = os.environ["SNAPSHOT_EMAIL_FROM"]
    password  = os.environ["SNAPSHOT_GMAIL_APP_PASSWORD"]

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg.attach(email.mime.text.MIMEText(plain_body, "plain"))
    msg.attach(email.mime.text.MIMEText(html_body,  "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_addr, password)
        server.sendmail(from_addr, to_addr, msg.as_string())

    print(f"Email sent to {to_addr}", file=sys.stderr)


def main() -> None:
    if not os.environ.get("ALPHA_VANTAGE_API_KEY"):
        print(
            "WARNING: ALPHA_VANTAGE_API_KEY not set — prices will fall back to Monarch cached values.",
            file=sys.stderr,
        )

    view_json = asyncio.run(_fetch_data())
    plain     = _render_table(view_json)
    print(plain)

    if os.environ.get("SNAPSHOT_GMAIL_APP_PASSWORD"):
        today   = date.today().strftime("%B %d, %Y")
        subject = f"Daily Investment Snapshot — {today}"
        html    = _render_html(view_json)
        _send_email(subject, html, plain)


if __name__ == "__main__":
    main()
