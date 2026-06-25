"""NSE index universes for ranking and live watchlists."""

NIFTY50 = (
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJFINANCE", "BAJAJFINSV", "BPCL", "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA",
    "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC", "INDUSINDBK", "INFY",
    "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SUNPHARMA", "TCS", "TATACONSUM",
    "TATAMOTORS", "TATASTEEL", "TECHM", "TITAN", "ULTRACEMCO", "UPL", "WIPRO",
)

# Nifty Next 50 — liquid large/mid caps (Yahoo .NS); deduped with Nifty 50 below.
NIFTY_NEXT50 = (
    "ABB", "ADANIENSOL", "AMBUJACEM", "ATGL", "AUROPHARMA", "BAJAJHLDNG", "BANKBARODA",
    "BERGEPAINT", "BOSCHLTD", "CANBK", "CHOLAFIN", "COLPAL", "CONCOR", "COROMANDEL",
    "DABUR", "DLF", "GAIL", "GODREJCP", "GODREJPROP", "HAVELLS", "HDFCAMC", "ICICIPRULI",
    "IDFCFIRSTB", "INDHOTEL", "INDIGO", "IOC", "IRCTC", "JINDALSTEL", "LICI", "LTIM",
    "MRF", "MOTHERSON", "NAUKRI", "NMDC", "PAGEIND", "PFC", "PIIND", "PNB", "RECLTD",
    "SAIL", "SBICARD", "SHREECEM", "SIEMENS", "TATAPOWER", "TRENT", "TVSMOTOR", "VBL",
    "VEDL", "ZYDUSLIFE", "DMART", "HAL", "BEL", "POLYCAB",
)


def nifty100() -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for sym in (*NIFTY50, *NIFTY_NEXT50):
        s = sym.upper()
        if s not in seen:
            seen.add(s)
            out.append(s)
    return tuple(out)
