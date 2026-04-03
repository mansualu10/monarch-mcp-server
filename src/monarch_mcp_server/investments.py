"""Investment aggregation helpers for Monarch holdings workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
_AV_BASE = "https://www.alphavantage.co/query"
_AV_RATE_SLEEP = 12.0  # seconds between calls — stays within 5 req/min free tier

CASH_LIKE_TYPES = {"cash"}
CASH_LIKE_TICKERS = {"SPAXX", "FDRXX", "QDERQ", "QACDS"}


@dataclass
class MarketSnapshot:
    """Latest market data for a tradable symbol."""

    price: float | None
    previous_month_price: float | None
    as_of: str | None
    source: str


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: str | None) -> str | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        return value


def _is_active_investment_account(account: dict[str, Any]) -> bool:
    return bool(account.get("is_active")) and account.get("type") == "brokerage"


def _normalize_symbol(symbol: str | None, fallback_name: str) -> str:
    cleaned = (symbol or "").strip()
    return cleaned or fallback_name.strip()


def _format_currency(value: float | None) -> str | None:
    if value is None:
        return None
    return f"${value:,.2f}"


def _format_quantity(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:,.4f}"


def _extract_monarch_price(node: dict[str, Any]) -> tuple[float | None, str | None]:
    security = node.get("security") or {}
    holdings = node.get("holdings") or []
    holding = holdings[0] if holdings else {}

    for price, timestamp in (
        (security.get("currentPrice"), security.get("currentPriceUpdatedAt")),
        (holding.get("closingPrice"), holding.get("closingPriceUpdatedAt")),
        (security.get("closingPrice"), security.get("closingPriceUpdatedAt")),
    ):
        parsed_price = _safe_float(price)
        if parsed_price is not None:
            return parsed_price, _parse_timestamp(timestamp)

    return None, None


def _looks_market_quotable(symbol: str, security_type: str | None) -> bool:
    if not symbol:
        return False
    if security_type in {"derivative", "cash", "other"}:
        return False
    if symbol in CASH_LIKE_TICKERS:
        return False
    return True


def get_market_snapshots(symbols: list[str]) -> dict[str, MarketSnapshot]:
    """Fetch latest prices for market-tradable symbols via Alpha Vantage."""
    if not ALPHA_VANTAGE_API_KEY:
        logger.warning("ALPHA_VANTAGE_API_KEY not set — skipping market price lookup")
        return {}

    snapshots: dict[str, MarketSnapshot] = {}

    for i, symbol in enumerate(symbols):
        if i > 0:
            time.sleep(_AV_RATE_SLEEP)
        try:
            url = (
                f"{_AV_BASE}?function=GLOBAL_QUOTE"
                f"&symbol={urllib.request.quote(symbol)}"
                f"&apikey={ALPHA_VANTAGE_API_KEY}"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())

            quote = data.get("Global Quote") or {}
            price = _safe_float(quote.get("05. price"))
            if price is None:
                logger.warning("No price returned by Alpha Vantage for %s", symbol)
                continue

            as_of = quote.get("07. latest trading day")

            snapshots[symbol] = MarketSnapshot(
                price=price,
                previous_month_price=None,  # not available on free tier
                as_of=as_of,
                source="alphavantage",
            )
        except (urllib.error.URLError, json.JSONDecodeError, Exception) as exc:
            logger.warning("Alpha Vantage lookup failed for %s: %s", symbol, exc)

    return snapshots


def _build_row(
    key: str,
    aggregate: dict[str, Any],
    market_snapshot: MarketSnapshot | None,
) -> dict[str, Any]:
    price = market_snapshot.price if market_snapshot and market_snapshot.price is not None else aggregate["monarch_price"]
    price_source = market_snapshot.source if market_snapshot and market_snapshot.price is not None else "monarch"
    price_as_of = market_snapshot.as_of if market_snapshot and market_snapshot.price is not None else aggregate["monarch_price_as_of"]
    total_value = None
    if price is not None:
        total_value = aggregate["quantity"] * price
    elif aggregate["monarch_total_value"] is not None:
        total_value = aggregate["monarch_total_value"]

    one_month_change_value = None
    one_month_change_percent = None
    if (
        market_snapshot
        and market_snapshot.price is not None
        and market_snapshot.previous_month_price is not None
    ):
        one_month_change_value = (
            market_snapshot.price - market_snapshot.previous_month_price
        ) * aggregate["quantity"]
        if market_snapshot.previous_month_price:
            one_month_change_percent = (
                (market_snapshot.price - market_snapshot.previous_month_price)
                / market_snapshot.previous_month_price
            ) * 100

    return {
        "symbol": key,
        "name": aggregate["name"],
        "type": aggregate["type"],
        "quantity": aggregate["quantity"],
        "quantity_display": _format_quantity(aggregate["quantity"]),
        "latest_price": price,
        "latest_price_display": _format_currency(price),
        "price_source": price_source,
        "price_as_of": price_as_of,
        "total_value": total_value,
        "total_value_display": _format_currency(total_value),
        "accounts": sorted(aggregate["accounts"]),
        "account_count": len(aggregate["accounts"]),
        "one_month_change_value": one_month_change_value,
        "one_month_change_value_display": _format_currency(one_month_change_value),
        "one_month_change_percent": one_month_change_percent,
    }


def build_investment_exec_view(
    accounts_json: str,
    holdings_by_account: dict[str, str],
) -> str:
    """Build an executive investments view from accounts and holdings payloads."""
    accounts = json.loads(accounts_json)
    active_accounts = [
        account for account in accounts if _is_active_investment_account(account)
    ]
    account_by_id = {account["id"]: account for account in active_accounts}

    aggregates: dict[str, dict[str, Any]] = {}

    for account_id, raw_holdings in holdings_by_account.items():
        account = account_by_id.get(account_id)
        if not account:
            continue

        payload = json.loads(raw_holdings)
        edges = (
            payload.get("portfolio", {})
            .get("aggregateHoldings", {})
            .get("edges", [])
        )
        for edge in edges:
            node = edge.get("node") or {}
            security = node.get("security") or {}
            holdings = node.get("holdings") or []
            holding = holdings[0] if holdings else {}

            symbol = _normalize_symbol(
                security.get("ticker") or holding.get("ticker"),
                security.get("name") or holding.get("name") or "Unknown Holding",
            )
            name = security.get("name") or holding.get("name") or symbol
            holding_type = (
                security.get("typeDisplay")
                or holding.get("typeDisplay")
                or security.get("type")
                or holding.get("type")
                or "Unknown"
            )

            quantity = _safe_float(node.get("quantity")) or 0.0
            monarch_total_value = _safe_float(node.get("totalValue"))
            monarch_price, monarch_price_as_of = _extract_monarch_price(node)

            aggregate = aggregates.setdefault(
                symbol,
                {
                    "name": name,
                    "type": holding_type,
                    "quantity": 0.0,
                    "accounts": set(),
                    "monarch_total_value": 0.0,
                    "monarch_price": monarch_price,
                    "monarch_price_as_of": monarch_price_as_of,
                    "market_quotable": _looks_market_quotable(
                        symbol, (security.get("type") or holding.get("type"))
                    ),
                },
            )

            aggregate["quantity"] += quantity
            aggregate["accounts"].add(account["name"])
            if monarch_total_value is not None:
                aggregate["monarch_total_value"] += monarch_total_value
            else:
                aggregate["monarch_total_value"] = None

            if aggregate["monarch_price"] is None and monarch_price is not None:
                aggregate["monarch_price"] = monarch_price
                aggregate["monarch_price_as_of"] = monarch_price_as_of

    market_symbols = sorted(
        symbol
        for symbol, aggregate in aggregates.items()
        if aggregate["market_quotable"]
    )
    market_snapshots = get_market_snapshots(market_symbols)

    rows = [
        _build_row(symbol, aggregate, market_snapshots.get(symbol))
        for symbol, aggregate in aggregates.items()
    ]
    rows.sort(key=lambda row: row["total_value"] or 0.0, reverse=True)

    total_value = sum((row["total_value"] or 0.0) for row in rows)
    one_month_change_value = sum(
        (row["one_month_change_value"] or 0.0) for row in rows
    )
    prior_value = total_value - one_month_change_value
    one_month_change_percent = None
    if prior_value:
        one_month_change_percent = (one_month_change_value / prior_value) * 100

    card = {
        "title": "Investments",
        "current_value": total_value,
        "current_value_display": _format_currency(total_value),
        "change_period": "1 month",
        "change_value": one_month_change_value,
        "change_value_display": _format_currency(one_month_change_value),
        "change_percent": one_month_change_percent,
        "trend": (
            "up"
            if one_month_change_value > 0
            else "down"
            if one_month_change_value < 0
            else "flat"
        ),
    }

    return json.dumps(
        {
            "card": card,
            "rows": rows,
            "meta": {
                "active_investment_account_count": len(active_accounts),
                "holding_count": len(rows),
                "price_sources": sorted({row["price_source"] for row in rows}),
            },
        },
        indent=2,
        default=str,
    )
