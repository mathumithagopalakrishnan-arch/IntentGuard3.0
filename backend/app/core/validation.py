"""Strict, stdlib-only validators. Money = integer minor units. Unknown keys rejected."""
CURRENCIES = {"USD", "EUR", "GBP", "INR", "AUD", "CAD"}
DISCLOSURES = {"shipping", "tax", "returns"}


class ValidationError(ValueError):
    pass


def _int(v, name, lo, hi):
    if type(v) is not int or not lo <= v <= hi:  # rejects bool, float, str
        raise ValidationError(f"{name} must be a whole number between {lo} and {hi}")
    return v


def _str(v, name, maxlen, minlen=1):
    if type(v) is not str or not minlen <= len(v.strip()) <= maxlen:
        raise ValidationError(f"{name} must be text of {minlen}-{maxlen} characters")
    return v.strip()


def _bool(v, name):
    if type(v) is not bool:
        raise ValidationError(f"{name} must be true or false")
    return v


def _list(v, name, maxn):
    if type(v) is not list or len(v) > maxn:
        raise ValidationError(f"{name} must be a list of at most {maxn} items")
    return v


def _disclosures(v, name):
    """List of known disclosure names. Rejects non-text items before hashing them (no TypeError -> no HTTP 500)."""
    v = _list(v, name, 3)
    if any(type(x) is not str for x in v) or not set(v) <= DISCLOSURES:
        raise ValidationError(f"{name} must be from {sorted(DISCLOSURES)}")
    return v


def _currency(v, name="currency"):
    if type(v) is not str or v not in CURRENCIES:
        raise ValidationError(f"{name} must be one of {sorted(CURRENCIES)}")
    return v


def _keys(d, allowed, name):
    if type(d) is not dict:
        raise ValidationError(f"{name} must be an object")
    extra = set(d) - allowed
    if extra:
        raise ValidationError(f"{name}: unexpected fields {sorted(extra)}")


def validate_intent(d) -> dict:
    _keys(d, {"category", "max_total", "currency", "max_quantity", "allow_subscription",
              "prohibited_terms", "max_shipping", "required_disclosures"}, "intent")
    for k in ("category", "max_total", "currency"):
        if k not in d:
            raise ValidationError(f"intent: missing {k}")
    disc = _disclosures(d.get("required_disclosures", ["shipping", "tax", "returns"]), "required_disclosures")
    if len(set(disc)) != len(disc):
        raise ValidationError("required_disclosures must not repeat a value")
    terms = [_str(t, "prohibited term", 40).lower() for t in _list(d.get("prohibited_terms", []), "prohibited_terms", 20)]
    ms = d.get("max_shipping")
    return {"category": _str(d["category"], "category", 80).lower(),
            "max_total": _int(d["max_total"], "max_total", 1, 10**9),
            "currency": _currency(d["currency"]),
            "max_quantity": _int(d.get("max_quantity", 1), "max_quantity", 1, 100),
            "allow_subscription": _bool(d.get("allow_subscription", False), "allow_subscription"),
            "prohibited_terms": sorted(set(terms)),
            "max_shipping": None if ms is None else _int(ms, "max_shipping", 0, 10**9),
            "required_disclosures": sorted(disc)}


def validate_offer(d) -> dict:
    _keys(d, {"merchant", "currency", "shipping", "tax", "disclosures", "claimed_total", "recurring_billing",
              "description", "terms", "items", "synthetic", "label"}, "offer")
    items = _list(d.get("items"), "items", 50)
    if not items:
        raise ValidationError("offer needs at least one item")
    out_items, seen = [], set()
    for it in items:
        _keys(it, {"id", "name", "description", "category", "unit_price", "recurring"}, "item")
        iid = _str(it.get("id"), "item id", 40)
        if iid in seen:
            raise ValidationError("duplicate item id")
        seen.add(iid)
        out_items.append({"id": iid, "name": _str(it.get("name"), "item name", 200),
                          "description": _str(it.get("description", " "), "item description", 2000, 0) if it.get("description") else "",
                          "category": _str(it.get("category"), "item category", 80).lower(),
                          "unit_price": _int(it.get("unit_price"), "unit_price", 0, 10**9),
                          "recurring": _bool(it.get("recurring", False), "recurring")})
    disc = _disclosures(d.get("disclosures", []), "disclosures")
    ct = d.get("claimed_total")
    return {"merchant": _str(d.get("merchant"), "merchant", 120), "currency": _currency(d.get("currency")),
            "shipping": _int(d.get("shipping", 0), "shipping", 0, 10**9), "tax": _int(d.get("tax", 0), "tax", 0, 10**9),
            "disclosures": sorted(set(disc)), "claimed_total": None if ct is None else _int(ct, "claimed_total", 0, 10**10),
            "recurring_billing": _bool(d.get("recurring_billing", False), "recurring_billing"),
            "description": _str(d["description"], "description", 5000, 0) if d.get("description") else "",
            "terms": _str(d["terms"], "terms", 5000, 0) if d.get("terms") else "",
            "items": out_items, "synthetic": _bool(d.get("synthetic", False), "synthetic"),
            "label": _str(d["label"], "label", 200, 0) if d.get("label") else ""}


def validate_cart(c) -> list:
    c = _list(c, "cart", 50)
    if not c:
        raise ValidationError("cart is empty")
    out, seen = [], set()
    for line in c:
        _keys(line, {"item_id", "qty", "unit_price"}, "cart line")
        iid = _str(line.get("item_id"), "item_id", 40)
        if iid in seen:
            raise ValidationError("duplicate cart line")
        seen.add(iid)
        out.append({"item_id": iid, "qty": _int(line.get("qty"), "qty", 1, 100),
                    "unit_price": _int(line.get("unit_price"), "unit_price", 0, 10**9)})
    return out
