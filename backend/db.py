"""Database layer: SQLite schema, connection helper, passwords and login tokens."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("BRANDSURE_DATA", os.path.join(BASE, "..", "data"))
DB_PATH = os.path.join(DATA_DIR, "brandsure.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
SECRET_PATH = os.path.join(DATA_DIR, "secret.key")

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  allow_ai INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT NULL,
  name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  role TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT NULL,
  kind TEXT NOT NULL, code TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '', severity TEXT NOT NULL DEFAULT 'Medium',
  category TEXT NOT NULL DEFAULT '', value TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active', confidential INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT NULL,
  number INTEGER NOT NULL, published_by INTEGER NOT NULL, snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT NULL,
  title TEXT NOT NULL, channel TEXT NOT NULL, audience TEXT NOT NULL,
  content_type TEXT NOT NULL, confidential INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL, created_by INTEGER NOT NULL, knowledge_version INTEGER NOT NULL DEFAULT 0,
  submitted_at TEXT, approved_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER NOT NULL, number INTEGER NOT NULL,
  content_text TEXT NOT NULL DEFAULT '', image_path TEXT NOT NULL DEFAULT '',
  alt_text TEXT NOT NULL DEFAULT '', caption TEXT NOT NULL DEFAULT '',
  text_color TEXT NOT NULL DEFAULT '', bg_color TEXT NOT NULL DEFAULT '',
  logo_width INTEGER NOT NULL DEFAULT 0, created_by INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, review_version_id INTEGER NOT NULL,
  type TEXT NOT NULL, severity TEXT NOT NULL, quote TEXT NOT NULL DEFAULT '',
  start_pos INTEGER NOT NULL DEFAULT -1, end_pos INTEGER NOT NULL DEFAULT -1,
  source_code TEXT NOT NULL DEFAULT 'NONE', why TEXT NOT NULL DEFAULT '',
  suggestion TEXT NOT NULL DEFAULT '', confidence TEXT NOT NULL DEFAULT 'medium',
  check_type TEXT NOT NULL DEFAULT 'rule', verdict TEXT NOT NULL DEFAULT 'violation',
  needs_reviewer INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'open', dismiss_reason TEXT NOT NULL DEFAULT '',
  dismiss_note TEXT NOT NULL DEFAULT '', escalated_to INTEGER, escalate_note TEXT NOT NULL DEFAULT '',
  resolved_by INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER NOT NULL, finding_id INTEGER,
  user_id INTEGER NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER NOT NULL, review_version_id INTEGER NOT NULL,
  decision TEXT NOT NULL, user_id INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '',
  override_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checks_run(
  id INTEGER PRIMARY KEY AUTOINCREMENT, review_version_id INTEGER NOT NULL,
  check_name TEXT NOT NULL, check_type TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT NULL, user_id INTEGER,
  action TEXT NOT NULL, target_type TEXT NOT NULL DEFAULT '', target_id INTEGER,
  detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_findings_rv ON findings(review_version_id);
CREATE INDEX IF NOT EXISTS ix_rv_review ON review_versions(review_id);
CREATE INDEX IF NOT EXISTS ix_audit_ws ON audit_log(workspace_id);
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with get_db() as c:
        c.executescript(SCHEMA)


# ---------- passwords ----------
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${h}"


def check_pw(pw, stored):
    try:
        salt = stored.split("$")[0]
    except Exception:
        return False
    return hmac.compare_digest(hash_pw(pw, salt), stored)


# ---------- signed login tokens ----------
def _secret():
    env = os.environ.get("BRANDSURE_SECRET")
    if env:
        return env.encode()
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "w") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_PATH) as f:
        return f.read().strip().encode()


def make_token(user_id, hours=12):
    payload = base64.urlsafe_b64encode(json.dumps({"u": user_id, "e": int(time.time()) + hours * 3600}).encode()).decode()
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token):
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    good = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except Exception:
        return None
    if data.get("e", 0) < time.time():
        return None
    return data.get("u")
