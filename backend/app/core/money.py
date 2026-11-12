"""Money is always integer minor units inside IntentGuard. PayPal wants decimal strings, so convert here, once."""
ZERO_DECIMAL = {"JPY", "HUF", "TWD"}  # PayPal currencies with no minor unit; not enabled by default


def to_paypal_value(minor: int, currency: str = "USD") -> str:
    """12345 -> '123.45'. Pure integer arithmetic: no floats, no rounding surprises."""
    if type(minor) is not int or minor < 0:
        raise ValueError("amount must be a non-negative integer of minor units")
    if currency in ZERO_DECIMAL:
        return str(minor)
    return f"{minor // 100}.{minor % 100:02d}"


def from_paypal_value(value: str, currency: str = "USD") -> int:
    """'123.45' -> 12345. Rejects anything that is not a plain decimal with at most two places."""
    if type(value) is not str:
        raise ValueError("PayPal amount must be a string")
    major, dot, frac = value.partition(".")
    if not major.isdigit() or (dot and (not frac.isdigit() or len(frac) > 2)):
        raise ValueError(f"unreadable PayPal amount: {value!r}")
    if currency in ZERO_DECIMAL:
        return int(major)
    return int(major) * 100 + int((frac + "00")[:2])
