"""Intent Drift: a plain attribute-by-attribute comparison of what the customer asked for and what the cart does.
It is derived from the same data as the verification checks and never overrides them. No AI."""
from .verification import category_matches


def compute_drift(intent: dict, offer: dict, cart: list[dict], verification: dict) -> list[dict]:
    cur = intent.get("currency")
    catalog = {i["id"]: i for i in offer.get("items", [])}
    failed = {c["id"]: c for c in verification.get("checks", []) if not c["passed"]}
    total = verification.get("server_total")
    qty = sum(c.get("qty", 0) for c in cart)
    cats = sorted({catalog[c["item_id"]]["category"] for c in cart if c.get("item_id") in catalog})
    shipping_limit = intent.get("max_shipping")
    recurring = bool(offer.get("recurring_billing") or any(catalog.get(c.get("item_id"), {}).get("recurring") for c in cart))
    fmt = lambda m: "n/a" if m is None else f"{m / 100:.2f} {cur}"

    def row(attr, wanted, got, check_ids, rule):
        bad = [failed[c] for c in check_ids if c in failed]
        return {"attribute": attr, "intent": wanted, "transaction": got, "drifted": bool(bad), "rule": rule,
                "evidence": "; ".join(b["detail"] for b in bad) if bad else "matches"}

    return [
        row("Product", intent.get("category"), ", ".join(cats) or "n/a", ["cart_items_exist", "category_matches"], "category_matches"),
        row("Total price", f"at most {fmt(intent.get('max_total'))}", fmt(total), ["within_budget", "claimed_total_matches", "cart_price_matches_offer"], "within_budget / claimed_total_matches / cart_price_matches_offer"),
        row("Currency", cur, offer.get("currency"), ["currency_matches"], "currency_matches"),
        row("Quantity", f"at most {intent.get('max_quantity', 1)}", str(qty), ["quantity_ok"], "quantity_ok"),
        row("Subscription", "allowed" if intent.get("allow_subscription") else "not allowed", "recurring billing present" if recurring else "none", ["recurring_billing_allowed"], "recurring_billing_allowed"),
        row("Shipping", "no limit set" if shipping_limit is None else f"at most {fmt(shipping_limit)}", fmt(offer.get("shipping", 0)), ["shipping_within_limit"], "shipping_within_limit"),
        row("Prohibited terms", ", ".join(intent.get("prohibited_terms", [])) or "none set", "found" if "no_prohibited_terms" in failed else "none found", ["no_prohibited_terms"], "no_prohibited_terms"),
        row("Disclosures", ", ".join(intent.get("required_disclosures", [])) or "none", "complete" if "required_disclosures_present" not in failed else "missing", ["required_disclosures_present"], "required_disclosures_present"),
        row("Merchant text safety", "treated as untrusted data", "high-severity instruction found" if "no_high_threats" in failed else "no high-severity finding", ["no_high_threats"], "no_high_threats"),
    ]


__all__ = ["compute_drift", "category_matches"]
