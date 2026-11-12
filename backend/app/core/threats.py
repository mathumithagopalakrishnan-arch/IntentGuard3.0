"""Deterministic detector for risky text in UNTRUSTED merchant content.
Rule-based on purpose: it never calls an AI and never obeys the text."""
import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)

RULES = [
    ("prompt_injection", "high", "ignore_instructions",
     r"ignore (all |any )?(previous|prior|above) (instructions|rules)"),
    ("prompt_injection", "high", "role_override",
     r"(\byou are now\b|\bact as\b|\bnew instructions?:|\bsystem prompt\b)"),
    ("prompt_injection", "high", "skip_verification",
     r"\b(skip|bypass|disable|turn off|do not run|don't run)\b.{0,20}\b(verification|safety checks?|security checks?|fraud checks?)\b"),
    ("prompt_injection", "high", "auto_approve",
     r"(approve|authori[sz]e|complete|confirm) (this |the )?(payment|purchase|order)( automatically| immediately)?"),
    ("prompt_injection", "high", "hide_from_user",
     r"(do not|don't|never) (tell|show|inform|mention).{0,30}(user|customer|buyer)"),
    ("deceptive_subscription", "high", "hidden_renewal",
     r"(auto[- ]?renew|renews? automatically|then (billed|charged)|recurring (charge|billing))"),
    ("deceptive_subscription", "medium", "free_trial",
     r"(free trial|trial ends)"),
    ("hidden_fee", "medium", "extra_fee_words",
     r"(processing fee|handling fee|convenience fee|service charge|added at checkout)"),
    ("manipulation", "low", "urgency",
     r"(only \d+ left|offer ends (in|today)|act now|last chance)"),
]


def normalize(text: str) -> str:
    """NFKC, drop zero-width characters, lowercase, collapse all whitespace runs (spaces, tabs, newlines)."""
    clean = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH).lower()
    return re.sub(r"\s+", " ", clean).strip()


def scan_text(text: str, source: str = "merchant") -> list[dict]:
    clean = normalize(text)
    findings = []
    for category, severity, rule_id, pattern in RULES:
        m = re.search(pattern, clean)
        if m:
            findings.append({
                "category": category, "severity": severity, "rule": rule_id,
                "source": source, "evidence": clean[max(0, m.start() - 20): m.end() + 20][:120],
                "origin": "deterministic_rule",
            })
    return findings


def scan_offer(offer: dict) -> list[dict]:
    findings = scan_text(offer.get("description", ""), "offer.description")
    findings += scan_text(offer.get("terms", ""), "offer.terms")
    for i, item in enumerate(offer.get("items", [])):
        findings += scan_text(item.get("name", "") + " " + item.get("description", ""), f"offer.items[{i}]")
    return findings
