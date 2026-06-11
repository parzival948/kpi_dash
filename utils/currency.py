def resolve_currency(currency):
    if currency == "Both":
        return "USD"
    return currency


def col_suffix(currency):
    if currency == "Local":
        return "_local"
    return "_usd"


def col_suffix_local():
    return "_local"


def col_suffix_usd():
    return "_usd"


def label(currency):
    if currency == "Local":
        return "Local"
    return "USD"


def fmt_money(currency, decimals=0):
    if currency == "Local":
        return f"{{:,.{decimals}f}}"
    return f"${{:,.{decimals}f}}"


def fmt_money_signed(currency, decimals=0):
    if currency == "Local":
        return f"{{:+,.{decimals}f}}"
    return f"${{:+,.{decimals}f}}"


def money_prefix(currency):
    if currency == "Local":
        return ""
    return "$"


def pick_col(df, base, currency):
    col = base + col_suffix(currency)
    if col in df.columns:
        return col
    return base


def pick_both(df, base):
    return f"{base}_usd", f"{base}_local"
