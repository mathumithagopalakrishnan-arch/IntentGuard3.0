import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS intents(
  id TEXT PRIMARY KEY, instruction TEXT NOT NULL, constraints_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
  source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT', created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS offers(
  id TEXT PRIMARY KEY, offer_json TEXT NOT NULL, synthetic INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS transactions(
  id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES intents(id), offer_id TEXT NOT NULL REFERENCES offers(id),
  cart_json TEXT NOT NULL, result_json TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE INDEX IF NOT EXISTS ix_tx_intent ON transactions(intent_id);
CREATE TABLE IF NOT EXISTS consents(
  id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL UNIQUE REFERENCES transactions(id), fingerprint TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('GRANTED','REJECTED')), used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  type TEXT NOT NULL, intent_id TEXT, transaction_id TEXT, detail_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_audit_tx ON audit_events(transaction_id);
CREATE INDEX IF NOT EXISTS ix_audit_intent ON audit_events(intent_id);
CREATE INDEX IF NOT EXISTS ix_audit_type ON audit_events(type);
CREATE TABLE IF NOT EXISTS payments(
  id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL UNIQUE REFERENCES transactions(id),
  state TEXT NOT NULL CHECK(state IN ('CREATING','ORDER_CREATED','CAPTURING','COMPLETED','FAILED','CANCELLED','EXPIRED','CAPTURE_PENDING')),
  amount_minor INTEGER NOT NULL, currency TEXT NOT NULL,
  create_request_id TEXT NOT NULL, capture_request_id TEXT,
  paypal_order_id TEXT, approve_url TEXT, paypal_status TEXT, capture_id TEXT, capture_status TEXT,
  error_code TEXT, error_message TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_order ON payments(paypal_order_id) WHERE paypal_order_id IS NOT NULL;
"""

# Added after the first release: a hash chain so edits or deletions in audit_events are detectable.
AUDIT_CHAIN_COLUMNS = (("prev_hash", "TEXT"), ("hash", "TEXT"))
# Added in 3.1: a consent now expires. NULL (older rows) is treated as created_at + the configured lifetime.
CONSENT_COLUMNS = (("expires_epoch", "REAL"),)


def connect(path):
    # FastAPI may run a sync dependency and its sync route in different worker threads.
    # Connections are scoped to one request and used sequentially, so thread migration is safe.
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)  # manual transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def apply_schema(conn):
    """Create tables if missing and upgrade older databases in place. Safe to run on every start."""
    conn.executescript(SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(audit_events)")}
    for col, typ in AUDIT_CHAIN_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE audit_events ADD COLUMN {col} {typ}")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(consents)")}
    for col, typ in CONSENT_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE consents ADD COLUMN {col} {typ}")


def init_db(path):
    conn = connect(path)
    apply_schema(conn)
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # readers do not block the writer; ignored for in-memory databases
    except Exception:
        pass
    conn.close()


@contextmanager
def tx(conn):
    """BEGIN IMMEDIATE takes the write lock up front, so check-then-write is atomic."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
