import json

from monarch_mcp_server import investments


def test_build_investment_exec_view_aggregates_symbols_across_accounts(monkeypatch):
    accounts = json.dumps(
        [
            {
                "id": "acct-1",
                "name": "Brokerage One",
                "type": "brokerage",
                "balance": 1000,
                "institution": "Fidelity",
                "is_active": True,
            },
            {
                "id": "acct-2",
                "name": "Brokerage Two",
                "type": "brokerage",
                "balance": 2000,
                "institution": "Chase",
                "is_active": True,
            },
        ]
    )
    holdings = {
        "acct-1": json.dumps(
            {
                "portfolio": {
                    "aggregateHoldings": {
                        "edges": [
                            {
                                "node": {
                                    "quantity": 10,
                                    "totalValue": 1000,
                                    "security": {
                                        "ticker": "MSFT",
                                        "name": "Microsoft Corporation",
                                        "type": "equity",
                                        "typeDisplay": "Stock",
                                        "currentPrice": 100,
                                        "currentPriceUpdatedAt": "2026-04-03T12:00:00+00:00",
                                    },
                                    "holdings": [],
                                }
                            }
                        ]
                    }
                }
            }
        ),
        "acct-2": json.dumps(
            {
                "portfolio": {
                    "aggregateHoldings": {
                        "edges": [
                            {
                                "node": {
                                    "quantity": 5,
                                    "totalValue": 500,
                                    "security": {
                                        "ticker": "MSFT",
                                        "name": "Microsoft Corporation",
                                        "type": "equity",
                                        "typeDisplay": "Stock",
                                        "currentPrice": 100,
                                        "currentPriceUpdatedAt": "2026-04-03T12:00:00+00:00",
                                    },
                                    "holdings": [],
                                }
                            }
                        ]
                    }
                }
            }
        ),
    }

    monkeypatch.setattr(
        investments,
        "get_market_snapshots",
        lambda symbols: {
            "MSFT": investments.MarketSnapshot(
                price=110.0,
                previous_month_price=100.0,
                as_of="2026-04-03T12:00:00+00:00",
                source="yfinance",
            )
        },
    )

    result = json.loads(investments.build_investment_exec_view(accounts, holdings))

    assert result["card"]["current_value"] == 1650.0
    assert round(result["card"]["change_value"], 2) == 150.0
    assert result["meta"]["active_investment_account_count"] == 2
    assert result["rows"][0]["symbol"] == "MSFT"
    assert result["rows"][0]["quantity"] == 15.0
    assert result["rows"][0]["accounts"] == ["Brokerage One", "Brokerage Two"]
