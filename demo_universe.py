#!/usr/bin/env python3
"""Shared curated ticker universes for the Yahoo-backed fundamental screens.

Symbol-selection input only: membership here implies nothing about a
company's fundamentals, and every screen computes comparisons WITHIN each
company. No KG reads; importing this module touches no files and no network.

Why two lists instead of one: the screens have different foci. The rotation
screen covers the book plus mega-cap rotation names; the momentum screen
covers semis/AI-capex names plus the value/non-semi portfolio. A single
union would screen names neither screen was designed to rank.
"""

ROTATION_TICKERS = """
AAPL MSFT NVDA AMZN GOOGL META AVGO AMD MU TSM
VTRS HPQ GM VALE PFE NVO ADBE PBR JPM XOM
""".split()

GROWTH_TICKERS = """
MU NVDA TSM WDC LITE AVGO AMD MRVL SNDK
VTRS HPQ GM VALE PFE NVO ADBE PBR AAPL MSFT
""".split()
