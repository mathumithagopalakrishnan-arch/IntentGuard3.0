"""Deterministic Transaction Integrity Engine. No AI. Money is integer minor units."""
import re
from .fingerprint import intent_fingerprint, sha256_hex
from .threats import normalize, scan_offer

REQUIRED_DISCLOSURES_DEFAULT = ["shipping", "tax", "returns"]


def recompute_total(offer: dict, cart: list[dict]) -> int:
    catalog = {i["id"]: i for i in offer["items"]}
    subtotal = sum(catalog[c["item_id"]]["unit_price"] * c["qty"] for c in cart)
    return subtotal + offer.get("shipping", 0) + offer.get("tax", 0)


def _tokens(text: str) -> set:
    """Lowercase words with a trailing plural 's' removed, so 'cables' matches 'cable'."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[^\W_]+", normalize(text))}


def category_matches(wanted: str, offered: str) -> bool:
    """The offered category must be the wanted one or a more specific form of it.
    'headphones' matches 'wireless headphones'. 'wireless headphones' does NOT match plain 'headphones'."""
    w = _tokens(wanted)
    return bool(w) and w <= _tokens(offered)


def term_found(term: str, text: str) -> bool:
    """Whole-word match, so a prohibited 'used' does not fire on 'focused'."""
    return re.search(r"(?<!\w)" + re.escape(normalize(term)) + r"(?!\w)", normalize(text)) is not None


def _check(cid, passed, detail, severity="block"):
    return {"id": cid, "passed": bool(passed), "severity": severity, "detail": detail}


def verify(intent: dict, offer: dict, cart: list[dict]) -> dict:
    checks = []
    catalog = {i["id"]: i for i in offer.get("items", [])}
    unknown = [c["item_id"] for c in cart if c.get("item_id") not in catalog]
    checks.append(_check("cart_items_exist", not unknown and cart, f"unknown items: {unknown}" if unknown else "all cart items are in the offer"))
    if unknown or not cart:
        return _finish(intent, offer, cart, checks, None)

    # Price manipulation: cart price must equal the offer price.
    mismatched = [c["item_id"] for c in cart if c.get("unit_price") != catalog[c["item_id"]]["unit_price"]]
    checks.append(_check("cart_price_matches_offer", not mismatched, f"price differs for {mismatched}" if mismatched else "cart prices match offer"))

    total = recompute_total(offer, cart)
    claimed = offer.get("claimed_total")
    checks.append(_check("claimed_total_matches", claimed is None or claimed == total, f"offer claims {claimed}, server computed {total}"))
    checks.append(_check("currency_matches", offer.get("currency") == intent.get("currency"), f"offer {offer.get('currency')} vs intent {intent.get('currency')}"))
    checks.append(_check("within_budget", total <= intent["max_total"], f"total {total} vs limit {intent['max_total']}"))

    qty = sum(c["qty"] for c in cart)
    checks.append(_check("quantity_ok", 1 <= qty <= intent.get("max_quantity", 1), f"qty {qty} vs max {intent.get('max_quantity', 1)}"))

    cats = {catalog[c["item_id"]]["category"] for c in cart}
    checks.append(_check("category_matches", all(category_matches(intent["category"], k) for k in cats),
                         f"cart categories {sorted(cats)} vs wanted {intent['category']}"))

    # Prohibited words are searched in the item name, its description, its category and the merchant name.
    text = " ".join(f"{catalog[c['item_id']]['name']} {catalog[c['item_id']].get('description', '')} {catalog[c['item_id']]['category']}"
                    for c in cart) + " " + offer.get("merchant", "")
    hit = [t for t in intent.get("prohibited_terms", []) if term_found(t, text)]
    checks.append(_check("no_prohibited_terms", not hit, f"prohibited terms found: {hit}" if hit else "none found"))

    recurring = offer.get("recurring_billing") or any(catalog[c["item_id"]].get("recurring") for c in cart)
    checks.append(_check("recurring_billing_allowed", not recurring or intent.get("allow_subscription", False), "recurring billing present but not allowed by intent" if recurring else "no recurring billing"))

    if intent.get("max_shipping") is not None:
        checks.append(_check("shipping_within_limit", offer.get("shipping", 0) <= intent["max_shipping"], f"shipping {offer.get('shipping', 0)} vs {intent['max_shipping']}"))

    missing = [d for d in intent.get("required_disclosures", REQUIRED_DISCLOSURES_DEFAULT) if d not in offer.get("disclosures", [])]
    checks.append(_check("required_disclosures_present", not missing, f"missing disclosures: {missing}" if missing else "all present"))

    return _finish(intent, offer, cart, checks, total)


def _finish(intent, offer, cart, checks, total):
    threats = scan_offer(offer)
    high = [t for t in threats if t["severity"] == "high"]
    checks.append(_check("no_high_threats", not high, f"{len(high)} high-severity threat(s)" if high else "none"))
    ok = all(c["passed"] for c in checks)
    return {
        "decision": "VERIFIED" if ok else "BLOCKED",
        "checks": checks, "threats": threats, "server_total": total,
        # Binds approval to this exact intent + offer + cart + total.
        "transaction_fingerprint": sha256_hex({
            "intent": intent_fingerprint(intent), "offer": offer, "cart": cart, "total": total}),
    }
