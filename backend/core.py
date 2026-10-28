"""Business logic: users, knowledge base, reviews, findings, approvals, insights, settings."""
import base64
import difflib
import io
import json
import os
import re
import secrets
import zipfile
from datetime import datetime
from xml.etree import ElementTree

from . import db, engine

ROLES = ("creator", "reviewer", "manager", "admin")
CHANNELS = ("Social post", "Email", "Web page", "Press release")
AUDIENCES = ("Customers", "Students", "Investors", "Internal")
KINDS = ("guideline", "glossary", "fact", "claim", "colour")
PREFIX = {"guideline": "G", "glossary": "T", "fact": "F", "claim": "C", "colour": "B"}
DISMISS_REASONS = ("Not applicable", "Rule is unclear", "Approved exception", "Other")
UNRESOLVED = ("open", "escalated")
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class Err(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


def need(user, *roles):
    if user["role"] not in roles:
        raise Err(403, "Your role is not allowed to do this.")


def rows(rs):
    return [dict(r) for r in rs]


def audit(c, user, action, ttype="", tid=None, detail=""):
    c.execute("INSERT INTO audit_log(workspace_id,user_id,action,target_type,target_id,detail,created_at) VALUES(?,?,?,?,?,?,?)",
              (user["workspace_id"], user["id"], action, ttype, tid, detail[:500], db.now()))


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "workspace_id": u["workspace_id"]}


# ================================================================ auth
def register(c, d):
    ws_name = (d.get("workspace_name") or "").strip()
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if not ws_name or not name or not email:
        raise Err(400, "Workspace name, your name and email are required.")
    if "@" not in email:
        raise Err(400, "Enter a valid email address.")
    if len(pw) < 8:
        raise Err(400, "Password must be at least 8 characters.")
    if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise Err(409, "That email is already registered.")
    wid = c.execute("INSERT INTO workspaces(name,created_at) VALUES(?,?)", (ws_name, db.now())).lastrowid
    uid = c.execute("INSERT INTO users(workspace_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                    (wid, name, email, db.hash_pw(pw), "admin", db.now())).lastrowid
    user = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    audit(c, user, "register", "workspace", wid, ws_name)
    return {"token": db.make_token(uid), "user": public_user(user)}


def login(c, d):
    email = (d.get("email") or "").strip().lower()
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not db.check_pw(d.get("password") or "", u["password_hash"]):
        raise Err(401, "Email or password is incorrect.")
    user = dict(u)
    audit(c, user, "login", "user", user["id"])
    return {"token": db.make_token(user["id"]), "user": public_user(user)}


# ================================================================ knowledge base
def next_code(c, ws, kind):
    existing = {r[0] for r in c.execute("SELECT code FROM knowledge_items WHERE workspace_id=? AND kind=?", (ws, kind))}
    n = len(existing) + 1
    while f"{PREFIX[kind]}{n}" in existing:
        n += 1
    return f"{PREFIX[kind]}{n}"


def list_knowledge(c, user, kind=None):
    q, args = "SELECT * FROM knowledge_items WHERE workspace_id=? AND status!='archived'", [user["workspace_id"]]
    if kind:
        q += " AND kind=?"
        args.append(kind)
    items = rows(c.execute(q + " ORDER BY id", args))
    ver = c.execute("SELECT MAX(number) FROM knowledge_versions WHERE workspace_id=?", (user["workspace_id"],)).fetchone()[0] or 0
    return {"items": items, "version": ver}


def _clean_item(d, kind):
    sev = d.get("severity") or "Medium"
    if sev not in ("High", "Medium", "Low"):
        raise Err(400, "Severity must be High, Medium or Low.")
    title = (d.get("title") or "").strip()
    if not title:
        raise Err(400, "A title is required.")
    status = d.get("status") or "active"
    if status not in ("active", "draft"):
        raise Err(400, "Status must be active or draft.")
    if kind == "claim" and (d.get("extra") or "Needs proof") not in ("Allowed", "Needs proof", "Forbidden"):
        raise Err(400, "Claim status must be Allowed, Needs proof or Forbidden.")
    return {"title": title[:300], "body": (d.get("body") or "")[:3000], "severity": sev,
            "category": (d.get("category") or "")[:200], "value": str(d.get("value") or "")[:200],
            "source": (d.get("source") or "")[:300], "extra": (d.get("extra") or "")[:100],
            "status": status, "confidential": 1 if d.get("confidential") else 0}


def save_knowledge(c, user, d, item_id=None):
    need(user, "manager", "admin")
    ws = user["workspace_id"]
    if item_id is None:
        kind = d.get("kind")
        if kind not in KINDS:
            raise Err(400, "Unknown item kind.")
        f = _clean_item(d, kind)
        code = next_code(c, ws, kind)
        iid = c.execute(
            "INSERT INTO knowledge_items(workspace_id,kind,code,title,body,severity,category,value,source,extra,status,confidential,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ws, kind, code, f["title"], f["body"], f["severity"], f["category"], f["value"], f["source"], f["extra"],
             f["status"], f["confidential"], db.now(), db.now())).lastrowid
        audit(c, user, "knowledge_add", "knowledge", iid, f"{code} {f['title']}")
        return dict(c.execute("SELECT * FROM knowledge_items WHERE id=?", (iid,)).fetchone())
    row = c.execute("SELECT * FROM knowledge_items WHERE id=? AND workspace_id=?", (item_id, ws)).fetchone()
    if not row:
        raise Err(404, "Item not found.")
    f = _clean_item({**dict(row), **d}, row["kind"])
    c.execute("UPDATE knowledge_items SET title=?,body=?,severity=?,category=?,value=?,source=?,extra=?,status=?,confidential=?,updated_at=? WHERE id=?",
              (f["title"], f["body"], f["severity"], f["category"], f["value"], f["source"], f["extra"], f["status"],
               f["confidential"], db.now(), item_id))
    audit(c, user, "knowledge_edit", "knowledge", item_id, f"{row['code']} {f['title']}")
    return dict(c.execute("SELECT * FROM knowledge_items WHERE id=?", (item_id,)).fetchone())


def archive_knowledge(c, user, item_id):
    need(user, "manager", "admin")
    row = c.execute("SELECT * FROM knowledge_items WHERE id=? AND workspace_id=?", (item_id, user["workspace_id"])).fetchone()
    if not row:
        raise Err(404, "Item not found.")
    c.execute("UPDATE knowledge_items SET status='archived', updated_at=? WHERE id=?", (db.now(), item_id))
    audit(c, user, "knowledge_archive", "knowledge", item_id, row["code"])
    return {"ok": True}


def bulk_knowledge(c, user, d):
    need(user, "manager", "admin")
    kind = d.get("kind")
    if kind not in KINDS:
        raise Err(400, "Unknown item kind.")
    out = []
    for it in (d.get("items") or [])[:200]:
        it = {**it, "kind": kind, "status": it.get("status") or "draft"}
        out.append(save_knowledge(c, user, it))
    return {"saved": len(out), "items": out}


def publish_version(c, user):
    need(user, "manager", "admin")
    ws = user["workspace_id"]
    ids = [r[0] for r in c.execute("SELECT id FROM knowledge_items WHERE workspace_id=? AND status='active' ORDER BY id", (ws,))]
    if not ids:
        raise Err(400, "There are no active items to publish.")
    n = (c.execute("SELECT MAX(number) FROM knowledge_versions WHERE workspace_id=?", (ws,)).fetchone()[0] or 0) + 1
    c.execute("INSERT INTO knowledge_versions(workspace_id,number,published_by,snapshot,created_at) VALUES(?,?,?,?,?)",
              (ws, n, user["id"], json.dumps(ids), db.now()))
    audit(c, user, "knowledge_publish", "knowledge_version", n, f"{len(ids)} items")
    return {"version": n, "items": len(ids)}


def items_for_version(c, ws, number):
    snap = c.execute("SELECT snapshot FROM knowledge_versions WHERE workspace_id=? AND number=?", (ws, number)).fetchone()
    if snap:
        ids = json.loads(snap[0])
        if ids:
            q = ",".join("?" * len(ids))
            return rows(c.execute(f"SELECT * FROM knowledge_items WHERE workspace_id=? AND id IN ({q}) ORDER BY id", [ws] + ids))
    return rows(c.execute("SELECT * FROM knowledge_items WHERE workspace_id=? AND status='active' ORDER BY id", (ws,)))


def extract_text(filename, b64):
    name = (filename or "").lower()
    try:
        data = base64.b64decode(b64 or "", validate=False)
    except Exception:
        raise Err(400, "The file could not be read.")
    if len(data) > 8_000_000:
        raise Err(400, "File is too large (limit 8 MB).")
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            info = z.getinfo("word/document.xml")
            if info.file_size > 20_000_000:
                raise Err(400, "Document is too large.")
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            root = ElementTree.fromstring(z.read("word/document.xml"))
            paras = ["".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p")]
            return "\n".join(paras)
        except Err:
            raise
        except Exception:
            raise Err(400, "That DOCX file could not be read.")
    if name.endswith(".pdf"):
        try:
            import pdfplumber
        except ImportError:
            raise Err(501, "PDF import needs the pdfplumber package (pip install pdfplumber).")
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:50])
        except Exception:
            raise Err(400, "That PDF could not be read.")
    raise Err(400, "Supported files: DOCX, PDF, MD, TXT.")


def import_preview(c, user, d):
    need(user, "manager", "admin")
    text = extract_text(d.get("filename"), d.get("data_b64"))
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if len(line) >= 15:
            out.append({"title": line[:70] + ("..." if len(line) > 70 else ""), "body": line,
                        "severity": "Medium", "category": "Tone"})
    if not out:
        raise Err(400, "No rules were found in that file.")
    return {"rules": out[:200]}


# ================================================================ reviews
def _save_image(d):
    b64, name = d.get("image_b64"), (d.get("image_name") or "image.png").lower()
    if not b64:
        return ""
    ext = os.path.splitext(name)[1]
    if ext not in IMG_EXT:
        raise Err(400, "Images must be PNG, JPG, GIF or WEBP.")
    try:
        data = base64.b64decode(b64)
    except Exception:
        raise Err(400, "The image could not be read.")
    if len(data) > 5_000_000:
        raise Err(400, "Image is too large (limit 5 MB).")
    fname = secrets.token_hex(12) + ext
    os.makedirs(db.UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(db.UPLOAD_DIR, fname), "wb") as f:
        f.write(data)
    return fname


def _get_review(c, user, rid):
    r = c.execute("SELECT r.*, u.name AS creator_name FROM reviews r JOIN users u ON u.id=r.created_by "
                  "WHERE r.id=? AND r.workspace_id=?", (rid, user["workspace_id"])).fetchone()
    if not r:
        raise Err(404, "Review not found.")
    return dict(r)


def _latest_version(c, rid):
    return dict(c.execute("SELECT * FROM review_versions WHERE review_id=? ORDER BY number DESC LIMIT 1", (rid,)).fetchone())


def _can_work(user, review):
    return user["role"] in ("manager", "admin") or (user["role"] == "creator" and review["created_by"] == user["id"])


def _unresolved_high(c, vid):
    return c.execute("SELECT COUNT(*) FROM findings WHERE review_version_id=? AND severity='High' AND state IN ('open','escalated')",
                     (vid,)).fetchone()[0]


def run_and_store(c, user, review, version, carry_from=None):
    """Run the engine on a review version and save findings + checks."""
    ws = user["workspace_id"]
    items = items_for_version(c, ws, review["knowledge_version"])
    image = None
    if review["content_type"] == "image":
        image = {"alt": version["alt_text"], "text_color": version["text_color"],
                 "bg_color": version["bg_color"], "logo_width": version["logo_width"]}
    allow_ai = bool(c.execute("SELECT allow_ai FROM workspaces WHERE id=?", (ws,)).fetchone()[0])
    findings, checks = engine.run_checks(version["content_text"], items, confidential=bool(review["confidential"]),
                                         allow_ai=allow_ai, image=image, ai_fn=engine.default_ai_fn())
    carry = {}
    if carry_from:
        for r in c.execute("SELECT * FROM findings WHERE review_version_id=? AND state IN ('dismissed','overridden','cleared')", (carry_from,)):
            carry[(r["source_code"], r["quote"].lower())] = dict(r)
    vid = version["id"]
    c.execute("DELETE FROM findings WHERE review_version_id=?", (vid,))
    c.execute("DELETE FROM checks_run WHERE review_version_id=?", (vid,))
    for ch in checks:
        c.execute("INSERT INTO checks_run(review_version_id,check_name,check_type,status,message) VALUES(?,?,?,?,?)",
                  (vid, ch["check_name"], ch["check_type"], ch["status"], ch["message"]))
    for f in findings:
        old = carry.get((f["source_code"], f["quote"].lower()))
        state = old["state"] if old else "open"
        c.execute("INSERT INTO findings(review_version_id,type,severity,quote,start_pos,end_pos,source_code,why,suggestion,confidence,"
                  "check_type,verdict,needs_reviewer,state,dismiss_reason,dismiss_note,resolved_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (vid, f["type"], f["severity"], f["quote"], f["start"], f["end"], f["source_code"], f["why"], f["suggestion"],
                   f["confidence"], f["check_type"], f["verdict"], 1 if f["needs_reviewer"] else 0, state,
                   old["dismiss_reason"] if old else "", old["dismiss_note"] if old else "", old["resolved_by"] if old else None, db.now()))
    return len(findings)


def create_review(c, user, d):
    need(user, "creator", "manager", "admin")
    title = (d.get("title") or "").strip()
    ctype = d.get("content_type") or "text"
    draft = bool(d.get("draft"))
    if not title:
        raise Err(400, "A title is required.")
    if (d.get("channel") or "") not in CHANNELS:
        raise Err(400, "Choose a channel.")
    if (d.get("audience") or "") not in AUDIENCES:
        raise Err(400, "Choose an audience.")
    if ctype not in ("text", "image"):
        raise Err(400, "Content type must be text or image.")
    text = (d.get("content_text") or d.get("caption") or "").strip() if ctype == "text" else (d.get("caption") or "").strip()
    if len(text) > 20000:
        raise Err(400, "Text is too long (limit 20,000 characters).")
    if not draft:
        if ctype == "text" and not text:
            raise Err(400, "Paste or upload some text to check.")
        if ctype == "image" and not d.get("image_b64"):
            raise Err(400, "Upload an image to check.")
    ws = user["workspace_id"]
    kv = c.execute("SELECT MAX(number) FROM knowledge_versions WHERE workspace_id=?", (ws,)).fetchone()[0] or 0
    rid = c.execute("INSERT INTO reviews(workspace_id,title,channel,audience,content_type,confidential,status,created_by,knowledge_version,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (ws, title[:200], d["channel"], d["audience"], ctype, 1 if d.get("confidential") else 0,
                     "draft" if draft else "checked", user["id"], kv, db.now(), db.now())).lastrowid
    img = _save_image(d) if ctype == "image" else ""
    vid = c.execute("INSERT INTO review_versions(review_id,number,content_text,image_path,alt_text,caption,text_color,bg_color,logo_width,created_by,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, 1, text, img, (d.get("alt_text") or "")[:500], (d.get("caption") or "")[:2000],
                     (d.get("text_color") or "")[:9], (d.get("bg_color") or "")[:9], int(d.get("logo_width") or 0),
                     user["id"], db.now())).lastrowid
    review = _get_review(c, user, rid)
    n = 0
    if not draft:
        n = run_and_store(c, user, review, dict(c.execute("SELECT * FROM review_versions WHERE id=?", (vid,)).fetchone()))
    audit(c, user, "review_create" if not draft else "review_draft", "review", rid, f"{title} ({n} findings)")
    return {"id": rid, "findings": n}


def get_review(c, user, rid, version=None):
    review = _get_review(c, user, rid)
    nums = [r[0] for r in c.execute("SELECT number FROM review_versions WHERE review_id=? ORDER BY number", (rid,))]
    latest = nums[-1]
    number = int(version) if version else latest
    v = c.execute("SELECT v.*, u.name AS author FROM review_versions v JOIN users u ON u.id=v.created_by WHERE review_id=? AND number=?",
                  (rid, number)).fetchone()
    if not v:
        raise Err(404, "Version not found.")
    v = dict(v)
    findings = rows(c.execute(
        "SELECT f.*, u.name AS escalated_name FROM findings f LEFT JOIN users u ON u.id=f.escalated_to "
        "WHERE review_version_id=? ORDER BY CASE severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, "
        "CASE WHEN start_pos<0 THEN 1000000 ELSE start_pos END", (v["id"],)))
    items = {i["code"]: i for i in items_for_version(c, user["workspace_id"], review["knowledge_version"])}
    for f in findings:
        f["source"] = None
        it = items.get(f["source_code"])
        if it:
            f["source"] = {"code": it["code"], "kind": it["kind"], "title": it["title"], "body": it["body"],
                           "value": it["value"], "source": it["source"], "extra": it["extra"]}
    checks = rows(c.execute("SELECT * FROM checks_run WHERE review_version_id=?", (v["id"],)))
    comments = rows(c.execute("SELECT m.*, u.name AS author FROM comments m JOIN users u ON u.id=m.user_id WHERE review_id=? ORDER BY m.id", (rid,)))
    history = rows(c.execute("SELECT a.action, a.detail, a.created_at, u.name AS author FROM audit_log a LEFT JOIN users u ON u.id=a.user_id "
                             "WHERE a.workspace_id=? AND a.target_type='review' AND a.target_id=? ORDER BY a.id",
                             (user["workspace_id"], rid)))
    approvals = rows(c.execute("SELECT a.*, u.name AS author FROM approvals a JOIN users u ON u.id=a.user_id WHERE review_id=? ORDER BY a.id", (rid,)))
    lv = _latest_version(c, rid)
    audit(c, user, "view", "review", rid, f"v{number}")
    ai_used = any(ch["check_type"] == "ai" and ch["status"] == "ok" for ch in checks)
    return {"review": review, "versions": nums, "version": v, "is_latest": number == latest, "findings": findings,
            "checks": checks, "comments": comments, "history": history, "approvals": approvals,
            "unresolved_high": _unresolved_high(c, lv["id"]), "ai_used": ai_used,
            "can_work": _can_work(user, review) and review["status"] != "approved"}


def new_version(c, user, rid, d, text_override=None):
    review = _get_review(c, user, rid)
    if not _can_work(user, review):
        raise Err(403, "Only the creator or a manager can edit this content.")
    if review["status"] == "approved":
        raise Err(409, "This review is approved and locked. Create a new review to change it.")
    last = _latest_version(c, rid)
    text = (text_override if text_override is not None else (d.get("content_text") if review["content_type"] == "text" else d.get("caption")))
    if text is None:
        text = last["content_text"]
    text = text.strip()
    if not text and review["content_type"] == "text":
        raise Err(400, "The text cannot be empty.")
    if len(text) > 20000:
        raise Err(400, "Text is too long (limit 20,000 characters).")
    fields = {k: d.get(k, last[k]) for k in ("alt_text", "caption", "text_color", "bg_color", "logo_width")}
    img = last["image_path"]
    if review["content_type"] == "image" and d.get("image_b64"):
        img = _save_image(d)
    if review["content_type"] == "image":
        fields["caption"] = text
    vid = c.execute("INSERT INTO review_versions(review_id,number,content_text,image_path,alt_text,caption,text_color,bg_color,logo_width,created_by,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, last["number"] + 1, text, img, str(fields["alt_text"])[:500], str(fields["caption"])[:2000],
                     str(fields["text_color"])[:9], str(fields["bg_color"])[:9], int(fields["logo_width"] or 0),
                     user["id"], db.now())).lastrowid
    c.execute("UPDATE reviews SET status='checked', updated_at=? WHERE id=?", (db.now(), rid))
    newv = dict(c.execute("SELECT * FROM review_versions WHERE id=?", (vid,)).fetchone())
    n = run_and_store(c, user, review, newv, carry_from=last["id"])
    audit(c, user, "review_edit", "review", rid, f"v{newv['number']} ({n} findings)")
    return {"version": newv["number"], "findings": n}


def _finding_ctx(c, user, fid):
    f = c.execute("SELECT f.*, v.review_id, v.number AS vnum, v.content_text FROM findings f JOIN review_versions v ON v.id=f.review_version_id "
                  "WHERE f.id=?", (fid,)).fetchone()
    if not f:
        raise Err(404, "Finding not found.")
    f = dict(f)
    review = _get_review(c, user, f["review_id"])
    latest = _latest_version(c, f["review_id"])
    return f, review, latest


def accept_finding(c, user, fid, custom=None):
    f, review, latest = _finding_ctx(c, user, fid)
    if not _can_work(user, review):
        raise Err(403, "Only the creator or a manager can apply fixes.")
    if f["review_version_id"] != latest["id"]:
        raise Err(409, "This finding belongs to an older version.")
    if f["state"] not in ("open",):
        raise Err(409, "This finding is already handled.")
    repl = (custom if custom is not None else f["suggestion"])
    if f["start_pos"] < 0 or repl is None or (custom is None and not f["suggestion"]):
        raise Err(400, "There is no automatic fix for this finding. Use Edit fix or edit the content.")
    text = latest["content_text"]
    new_text = text[:f["start_pos"]] + repl + text[f["end_pos"]:]
    c.execute("UPDATE findings SET state='fixed', resolved_by=? WHERE id=?", (user["id"], fid))
    res = new_version(c, user, f["review_id"], {}, text_override=new_text)
    audit(c, user, "finding_edit" if custom is not None else "finding_accept", "review", f["review_id"], f"{f['source_code']} '{f['quote']}' -> '{repl}'")
    return res


def dismiss_finding(c, user, fid, d):
    f, review, latest = _finding_ctx(c, user, fid)
    if not _can_work(user, review):
        raise Err(403, "Only the creator or a manager can dismiss findings.")
    if review["status"] == "approved":
        raise Err(409, "This review is approved and locked.")
    if f["review_version_id"] != latest["id"]:
        raise Err(409, "This finding belongs to an older version.")
    reason = d.get("reason")
    if reason not in DISMISS_REASONS:
        raise Err(400, "Choose a reason for dismissing.")
    c.execute("UPDATE findings SET state='dismissed', dismiss_reason=?, dismiss_note=?, resolved_by=? WHERE id=?",
              (reason, (d.get("note") or "")[:500], user["id"], fid))
    audit(c, user, "finding_dismiss", "review", f["review_id"], f"{f['source_code']} '{f['quote']}' reason={reason}")
    return {"ok": True}


def escalate_finding(c, user, fid, d):
    f, review, latest = _finding_ctx(c, user, fid)
    if not _can_work(user, review):
        raise Err(403, "Only the creator or a manager can escalate findings.")
    if f["review_version_id"] != latest["id"]:
        raise Err(409, "This finding belongs to an older version.")
    rv = c.execute("SELECT * FROM users WHERE id=? AND workspace_id=? AND role IN ('reviewer','manager','admin')",
                   (d.get("reviewer_id"), user["workspace_id"])).fetchone()
    if not rv:
        raise Err(400, "Choose a reviewer.")
    c.execute("UPDATE findings SET state='escalated', escalated_to=?, escalate_note=? WHERE id=?",
              (rv["id"], (d.get("note") or "")[:500], fid))
    audit(c, user, "finding_escalate", "review", f["review_id"], f"{f['source_code']} to {rv['name']}")
    return {"ok": True}


def clear_finding(c, user, fid, d):
    need(user, "reviewer", "manager", "admin")
    f, review, latest = _finding_ctx(c, user, fid)
    if f["state"] != "escalated":
        raise Err(409, "Only escalated findings can be cleared by a reviewer.")
    note = (d.get("note") or "").strip()
    if not note:
        raise Err(400, "Add a note explaining your decision.")
    c.execute("UPDATE findings SET state='cleared', dismiss_reason='Reviewer cleared', dismiss_note=?, resolved_by=? WHERE id=?",
              (note[:500], user["id"], fid))
    audit(c, user, "finding_clear", "review", f["review_id"], f"{f['source_code']}: {note}")
    return {"ok": True}


def override_finding(c, user, fid, d):
    need(user, "manager", "admin")
    f, review, latest = _finding_ctx(c, user, fid)
    if f["state"] not in UNRESOLVED:
        raise Err(409, "This finding is already handled.")
    just = (d.get("justification") or "").strip()
    if not just:
        raise Err(400, "A written justification is required.")
    c.execute("UPDATE findings SET state='overridden', dismiss_reason='Manager override', dismiss_note=?, resolved_by=? WHERE id=?",
              (just[:500], user["id"], fid))
    audit(c, user, "finding_override", "review", f["review_id"], f"{f['source_code']}: {just}")
    return {"ok": True}


def submit_review(c, user, rid):
    review = _get_review(c, user, rid)
    if not _can_work(user, review):
        raise Err(403, "Only the creator or a manager can submit this review.")
    if review["status"] not in ("checked", "changes_requested"):
        raise Err(409, "Only a checked review can be submitted (current status: %s)." % review["status"])
    latest = _latest_version(c, rid)
    n = _unresolved_high(c, latest["id"])
    if n:
        raise Err(400, f"{n} High finding(s) are still open. Fix them, dismiss them with a reason, or ask a manager to override.")
    c.execute("UPDATE reviews SET status='in_review', submitted_at=COALESCE(submitted_at, ?), updated_at=? WHERE id=?",
              (db.now(), db.now(), rid))
    audit(c, user, "review_submit", "review", rid)
    return {"status": "in_review"}


def approve_review(c, user, rid, d):
    need(user, "reviewer", "manager", "admin")
    review = _get_review(c, user, rid)
    if review["status"] != "in_review":
        raise Err(409, "Only reviews that are in review can be approved.")
    latest = _latest_version(c, rid)
    n = _unresolved_high(c, latest["id"])
    reason = (d.get("override_reason") or "").strip()
    if n:
        if user["role"] == "reviewer":
            raise Err(403, "High findings are still open. Only a manager can approve with an override.")
        if not reason:
            raise Err(400, f"{n} High finding(s) are still open. Enter an override reason to approve anyway.")
    c.execute("INSERT INTO approvals(review_id,review_version_id,decision,user_id,note,override_reason,created_at) VALUES(?,?,?,?,?,?,?)",
              (rid, latest["id"], "approved", user["id"], (d.get("note") or "")[:500], reason[:500], db.now()))
    c.execute("UPDATE reviews SET status='approved', approved_at=?, updated_at=? WHERE id=?", (db.now(), db.now(), rid))
    audit(c, user, "review_approve", "review", rid, f"v{latest['number']}" + (f" override: {reason}" if n else ""))
    return {"status": "approved"}


def request_changes(c, user, rid, d):
    need(user, "reviewer", "manager", "admin")
    review = _get_review(c, user, rid)
    if review["status"] != "in_review":
        raise Err(409, "Only reviews that are in review can be sent back.")
    note = (d.get("note") or "").strip()
    if not note:
        raise Err(400, "Add a comment explaining what to change.")
    latest = _latest_version(c, rid)
    c.execute("INSERT INTO approvals(review_id,review_version_id,decision,user_id,note,created_at) VALUES(?,?,?,?,?,?)",
              (rid, latest["id"], "changes_requested", user["id"], note[:500], db.now()))
    c.execute("INSERT INTO comments(review_id,finding_id,user_id,body,created_at) VALUES(?,?,?,?,?)",
              (rid, None, user["id"], "Changes requested: " + note[:500], db.now()))
    c.execute("UPDATE reviews SET status='changes_requested', updated_at=? WHERE id=?", (db.now(), rid))
    audit(c, user, "review_request_changes", "review", rid, note)
    return {"status": "changes_requested"}


def add_comment(c, user, d):
    rid = d.get("review_id")
    _get_review(c, user, rid)
    body = (d.get("body") or "").strip()
    if not body:
        raise Err(400, "Write a comment first.")
    fid = d.get("finding_id")
    if fid:
        f, _, _ = _finding_ctx(c, user, fid)
        if f["review_id"] != rid:
            raise Err(400, "That finding does not belong to this review.")
    c.execute("INSERT INTO comments(review_id,finding_id,user_id,body,created_at) VALUES(?,?,?,?,?)",
              (rid, fid, user["id"], body[:2000], db.now()))
    audit(c, user, "comment", "review", rid, body[:80])
    return {"ok": True}


def diff_versions(c, user, rid, a, b):
    _get_review(c, user, rid)
    va = c.execute("SELECT content_text FROM review_versions WHERE review_id=? AND number=?", (rid, a)).fetchone()
    vb = c.execute("SELECT content_text FROM review_versions WHERE review_id=? AND number=?", (rid, b)).fetchone()
    if not va or not vb:
        raise Err(404, "Version not found.")
    ta, tb = re.findall(r"\s+|\w+|[^\w\s]", va[0]), re.findall(r"\s+|\w+|[^\w\s]", vb[0])
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"t": "eq", "s": "".join(ta[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"t": "del", "s": "".join(ta[i1:i2])})
            if j2 > j1:
                ops.append({"t": "ins", "s": "".join(tb[j1:j2])})
    return {"ops": ops}


# ================================================================ lists
def reviewers(c, user):
    return rows(c.execute("SELECT id,name,role FROM users WHERE workspace_id=? AND role IN ('reviewer','manager','admin') ORDER BY name", (user["workspace_id"],)))


def _review_rows(c, user, where, args):
    out = rows(c.execute(
        "SELECT r.id,r.title,r.channel,r.status,r.updated_at,r.submitted_at,u.name AS creator_name, "
        "(SELECT MAX(number) FROM review_versions WHERE review_id=r.id) AS version "
        f"FROM reviews r JOIN users u ON u.id=r.created_by WHERE r.workspace_id=? {where} ORDER BY r.updated_at DESC, r.id DESC LIMIT 200",
        [user["workspace_id"]] + args))
    for r in out:
        lv = c.execute("SELECT id FROM review_versions WHERE review_id=? ORDER BY number DESC LIMIT 1", (r["id"],)).fetchone()[0]
        r["open_findings"] = c.execute("SELECT COUNT(*) FROM findings WHERE review_version_id=? AND state IN ('open','escalated')", (lv,)).fetchone()[0]
        r["high"] = _unresolved_high(c, lv)
    return out


def dashboard(c, user):
    counts = {"drafts": 0, "in_review": 0, "changes_requested": 0, "approved": 0}
    for r in c.execute("SELECT status, COUNT(*) FROM reviews WHERE workspace_id=? GROUP BY status", (user["workspace_id"],)):
        key = {"draft": "drafts", "checked": "drafts"}.get(r[0], r[0])
        counts[key] = counts.get(key, 0) + r[1]
    recent = _review_rows(c, user, "", [])
    if user["role"] == "creator":
        action = [r for r in recent if r["status"] in ("changes_requested", "checked", "draft") and
                  c.execute("SELECT created_by FROM reviews WHERE id=?", (r["id"],)).fetchone()[0] == user["id"]]
    else:
        mine = {x[0] for x in c.execute(
            "SELECT DISTINCT v.review_id FROM findings f JOIN review_versions v ON v.id=f.review_version_id WHERE f.state='escalated' AND f.escalated_to=?",
            (user["id"],))}
        action = [r for r in recent if r["status"] == "in_review" or r["id"] in mine]
    return {"counts": counts, "action": action[:10], "recent": recent[:30]}


def approvals_list(c, user, tab):
    need(user, "reviewer", "manager", "admin")
    if tab == "changes":
        return {"rows": _review_rows(c, user, "AND r.status='changes_requested'", [])}
    if tab == "approved":
        return {"rows": _review_rows(c, user, "AND r.status='approved'", [])}
    mine = [x[0] for x in c.execute(
        "SELECT DISTINCT v.review_id FROM findings f JOIN review_versions v ON v.id=f.review_version_id WHERE f.state='escalated' AND f.escalated_to=?",
        (user["id"],))]
    marks = ",".join("?" * len(mine)) or "NULL"
    return {"rows": _review_rows(c, user, f"AND (r.status='in_review' OR r.id IN ({marks}))", mine)}


# ================================================================ insights
def insights(c, user, days):
    need(user, "manager", "admin")
    ws = user["workspace_id"]
    since = ""
    args = [ws]
    if days:
        since = " AND r.created_at >= datetime('now', ?)"
        args.append(f"-{int(days)} days")
    data = c.execute(
        "SELECT r.id AS rid, f.source_code, f.quote, f.state, f.dismiss_reason FROM findings f "
        "JOIN review_versions v ON v.id=f.review_version_id JOIN reviews r ON r.id=v.review_id "
        f"WHERE r.workspace_id=? {since}", args).fetchall()
    keys = {}
    for r in data:
        k = (r["rid"], r["source_code"], r["quote"].lower())
        e = keys.setdefault(k, {"dismissed": False, "unclear": False})
        if r["state"] == "dismissed":
            e["dismissed"] = True
            if r["dismiss_reason"] == "Rule is unclear":
                e["unclear"] = True
    titles = {r["code"]: r["title"] for r in c.execute("SELECT code,title FROM knowledge_items WHERE workspace_id=?", (ws,))}
    per = {}
    for (rid, code, q), e in keys.items():
        p = per.setdefault(code, {"code": code, "total": 0, "dismissed": 0, "unclear": 0})
        p["total"] += 1
        p["dismissed"] += 1 if e["dismissed"] else 0
        p["unclear"] += 1 if e["unclear"] else 0
    for p in per.values():
        p["title"] = titles.get(p["code"], "No approved source" if p["code"] == "NONE" else p["code"])
        p["rate"] = round(100 * p["dismissed"] / p["total"]) if p["total"] else 0
    top = sorted(per.values(), key=lambda p: -p["total"])[:10]
    dismissed = sorted([p for p in per.values() if p["dismissed"] and p["code"] != "NONE"], key=lambda p: (-p["rate"], -p["dismissed"]))[:10]
    unclear = [p for p in per.values() if p["unclear"] >= 2 and p["code"] != "NONE"]
    unclear.sort(key=lambda p: -p["unclear"])
    rv = c.execute(f"SELECT r.id, r.submitted_at, r.approved_at, (SELECT COUNT(*) FROM review_versions WHERE review_id=r.id) AS n "
                   f"FROM reviews r WHERE r.workspace_id=? {since}", args).fetchall()
    hours = []
    for r in rv:
        if r["submitted_at"] and r["approved_at"]:
            a = datetime.fromisoformat(r["submitted_at"].rstrip("Z"))
            b = datetime.fromisoformat(r["approved_at"].rstrip("Z"))
            hours.append((b - a).total_seconds() / 3600)
    return {"top": top, "dismissed": dismissed, "unclear": unclear,
            "avg_hours": round(sum(hours) / len(hours), 2) if hours else None,
            "avg_rounds": round(sum(r["n"] for r in rv) / len(rv), 1) if rv else None,
            "reviews": len(rv), "approved": len(hours)}


def reviews_for_code(c, user, code):
    need(user, "manager", "admin")
    return rows(c.execute(
        "SELECT DISTINCT r.id, r.title, r.status, r.channel FROM findings f JOIN review_versions v ON v.id=f.review_version_id "
        "JOIN reviews r ON r.id=v.review_id WHERE r.workspace_id=? AND f.source_code=? ORDER BY r.id DESC LIMIT 50",
        (user["workspace_id"], code)))


# ================================================================ settings
def list_users(c, user):
    return rows(c.execute("SELECT id,name,email,role FROM users WHERE workspace_id=? ORDER BY id", (user["workspace_id"],)))


def invite_user(c, user, d):
    need(user, "admin")
    name, email, role = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower(), d.get("role")
    if not name or "@" not in email:
        raise Err(400, "Enter a name and a valid email.")
    if role not in ROLES:
        raise Err(400, "Choose a role.")
    if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise Err(409, "That email is already registered.")
    temp = secrets.token_urlsafe(8)
    uid = c.execute("INSERT INTO users(workspace_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                    (user["workspace_id"], name, email, db.hash_pw(temp), role, db.now())).lastrowid
    audit(c, user, "user_invite", "user", uid, f"{email} as {role}")
    return {"id": uid, "temp_password": temp}


def change_role(c, user, uid, d):
    need(user, "admin")
    role = d.get("role")
    if role not in ROLES:
        raise Err(400, "Choose a role.")
    target = c.execute("SELECT * FROM users WHERE id=? AND workspace_id=?", (uid, user["workspace_id"])).fetchone()
    if not target:
        raise Err(404, "User not found.")
    if target["role"] == "admin" and role != "admin" and c.execute(
            "SELECT COUNT(*) FROM users WHERE workspace_id=? AND role='admin'", (user["workspace_id"],)).fetchone()[0] <= 1:
        raise Err(400, "There must be at least one admin.")
    c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    audit(c, user, "user_role", "user", uid, f"{target['email']} -> {role}")
    return {"ok": True}


def remove_user(c, user, uid):
    need(user, "admin")
    target = c.execute("SELECT * FROM users WHERE id=? AND workspace_id=?", (uid, user["workspace_id"])).fetchone()
    if not target:
        raise Err(404, "User not found.")
    if uid == user["id"]:
        raise Err(400, "You cannot remove yourself.")
    if c.execute("SELECT 1 FROM reviews WHERE created_by=? LIMIT 1", (uid,)).fetchone():
        raise Err(409, "This user created reviews, so they cannot be removed. Change their role instead.")
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    audit(c, user, "user_remove", "user", uid, target["email"])
    return {"ok": True}


def ai_settings(c, user):
    allow = bool(c.execute("SELECT allow_ai FROM workspaces WHERE id=?", (user["workspace_id"],)).fetchone()[0])
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    services = [
        {"name": "BrandSure rule engine (runs on this server)", "purpose": "Glossary, claim rules, numeric fact checks, style rules, image contrast and palette checks",
         "data_sent": "Nothing leaves the server", "confidential": "Always allowed", "active": True},
        {"name": "Anthropic Claude API (optional)", "purpose": "Tone and claim judgement with citations that are re-checked in code",
         "data_sent": "Draft text plus the non-confidential rules and facts needed for the check",
         "confidential": "Confidential reviews and confidential rules are never sent",
         "active": allow and key, "note": ("Switched off by an admin" if not allow else "No API key set on the server" if not key else "Active")},
    ]
    return {"allow_ai": allow, "key_present": key, "services": services}


def set_ai(c, user, d):
    need(user, "admin")
    c.execute("UPDATE workspaces SET allow_ai=? WHERE id=?", (1 if d.get("allow_ai") else 0, user["workspace_id"]))
    audit(c, user, "settings_ai", "workspace", user["workspace_id"], "allow_ai=%s" % bool(d.get("allow_ai")))
    return ai_settings(c, user)


def audit_list(c, user, uid=None):
    need(user, "admin", "manager")
    q = ("SELECT a.id,a.action,a.target_type,a.target_id,a.detail,a.created_at,u.name AS user_name FROM audit_log a "
         "LEFT JOIN users u ON u.id=a.user_id WHERE a.workspace_id=?")
    args = [user["workspace_id"]]
    if uid:
        q += " AND a.user_id=?"
        args.append(uid)
    return {"rows": rows(c.execute(q + " ORDER BY a.id DESC LIMIT 500", args))}


# ================================================================ approval record (PDF)
def approval_record_pdf(c, user, rid):
    review = _get_review(c, user, rid)
    if review["status"] != "approved":
        raise Err(409, "Only approved reviews have an approval record.")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        raise Err(501, "PDF export needs the reportlab package (pip install reportlab).")
    ap = c.execute("SELECT a.*, u.name AS author FROM approvals a JOIN users u ON u.id=a.user_id WHERE review_id=? AND decision='approved' ORDER BY a.id DESC LIMIT 1", (rid,)).fetchone()
    latest = _latest_version(c, rid)
    checks = rows(c.execute("SELECT * FROM checks_run WHERE review_version_id=?", (latest["id"],)))
    buf = io.BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    y = 270 * mm
    p.setFont("Helvetica-Bold", 18)
    p.drawString(20 * mm, y, "BrandSure approval record")
    y -= 12 * mm
    p.setFont("Helvetica", 11)
    lines = [f"Title: {review['title']}", f"Channel: {review['channel']}   Audience: {review['audience']}",
             f"Approved version: v{latest['number']}", f"Approved by: {ap['author']}", f"Approved at (UTC): {ap['created_at']}",
             f"Knowledge version used: {review['knowledge_version'] or 'unpublished set'}",
             f"Confidential item: {'yes' if review['confidential'] else 'no'}",
             f"Override reason: {ap['override_reason'] or 'none'}", "", "Checks run on the approved version:"]
    for ch in checks:
        lines.append(f" - [{ch['check_type']}] {ch['check_name']}: {ch['status']} ({ch['message']})"[:110])
    for ln in lines:
        p.drawString(20 * mm, y, ln[:110])
        y -= 7 * mm
    p.save()
    audit(c, user, "export_record", "review", rid)
    return buf.getvalue()
