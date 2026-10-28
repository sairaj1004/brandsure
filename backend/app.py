"""BrandSure web server (Flask). Serves the JSON API under /api and the frontend files."""
import os
from functools import wraps

from flask import Flask, Response, g, jsonify, request, send_from_directory

from . import core, db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


@app.errorhandler(core.Err)
def on_err(e):
    return jsonify({"detail": e.msg}), e.status


@app.errorhandler(404)
def on_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"detail": "Not found."}), 404
    return send_from_directory(FRONTEND, "index.html")


@app.errorhandler(413)
def on_413(e):
    return jsonify({"detail": "That upload is too large."}), 413


@app.errorhandler(500)
def on_500(e):
    return jsonify({"detail": "Something went wrong on the server."}), 500


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


def body():
    return request.get_json(silent=True) or {}


def authed(fn):
    """Run the route inside one DB transaction with the logged-in user: fn(c, user, ...)."""
    @wraps(fn)
    def wrapper(*a, **k):
        hdr = request.headers.get("Authorization", "")
        token = hdr[7:] if hdr.startswith("Bearer ") else request.args.get("t")
        uid = db.verify_token(token)
        if not uid:
            raise core.Err(401, "Please sign in.")
        with db.get_db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not row:
                raise core.Err(401, "Please sign in.")
            result = fn(c, dict(row), *a, **k)
        return result if isinstance(result, Response) else jsonify(result)
    return wrapper


def open_route(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        with db.get_db() as c:
            return jsonify(fn(c, *a, **k))
    return wrapper


# ---------------------------------------------------------------- auth
@app.post("/api/auth/register")
@open_route
def r_register(c):
    return core.register(c, body())


@app.post("/api/auth/login")
@open_route
def r_login(c):
    return core.login(c, body())


@app.get("/api/me")
@authed
def r_me(c, user):
    return core.public_user(user)


@app.get("/api/health")
def r_health():
    return jsonify({"ok": True})


# ---------------------------------------------------------------- dashboard & lists
@app.get("/api/dashboard")
@authed
def r_dashboard(c, user):
    return core.dashboard(c, user)


@app.get("/api/reviewers")
@authed
def r_reviewers(c, user):
    return core.reviewers(c, user)


@app.get("/api/approvals")
@authed
def r_approvals(c, user):
    return core.approvals_list(c, user, request.args.get("tab", "waiting"))


@app.get("/api/insights")
@authed
def r_insights(c, user):
    days = request.args.get("days", "")
    return core.insights(c, user, int(days) if days.isdigit() else 0)


@app.get("/api/insights/code/<code>")
@authed
def r_insights_code(c, user, code):
    return core.reviews_for_code(c, user, code)


# ---------------------------------------------------------------- knowledge
@app.get("/api/knowledge")
@authed
def r_kn_list(c, user):
    return core.list_knowledge(c, user, request.args.get("kind"))


@app.post("/api/knowledge")
@authed
def r_kn_add(c, user):
    return core.save_knowledge(c, user, body())


@app.put("/api/knowledge/<int:item_id>")
@authed
def r_kn_edit(c, user, item_id):
    return core.save_knowledge(c, user, body(), item_id)


@app.post("/api/knowledge/<int:item_id>/archive")
@authed
def r_kn_archive(c, user, item_id):
    return core.archive_knowledge(c, user, item_id)


@app.post("/api/knowledge/import")
@authed
def r_kn_import(c, user):
    return core.import_preview(c, user, body())


@app.post("/api/knowledge/bulk")
@authed
def r_kn_bulk(c, user):
    return core.bulk_knowledge(c, user, body())


@app.post("/api/knowledge/publish")
@authed
def r_kn_publish(c, user):
    return core.publish_version(c, user)


@app.post("/api/extract")
@authed
def r_extract(c, user):
    d = body()
    return {"text": core.extract_text(d.get("filename"), d.get("data_b64"))}


# ---------------------------------------------------------------- reviews
@app.post("/api/reviews")
@authed
def r_review_create(c, user):
    return core.create_review(c, user, body())


@app.get("/api/reviews/<int:rid>")
@authed
def r_review_get(c, user, rid):
    return core.get_review(c, user, rid, request.args.get("version"))


@app.post("/api/reviews/<int:rid>/versions")
@authed
def r_review_version(c, user, rid):
    return core.new_version(c, user, rid, body())


@app.get("/api/reviews/<int:rid>/diff")
@authed
def r_review_diff(c, user, rid):
    return core.diff_versions(c, user, rid, request.args.get("a", type=int), request.args.get("b", type=int))


@app.post("/api/reviews/<int:rid>/submit")
@authed
def r_review_submit(c, user, rid):
    return core.submit_review(c, user, rid)


@app.post("/api/reviews/<int:rid>/approve")
@authed
def r_review_approve(c, user, rid):
    return core.approve_review(c, user, rid, body())


@app.post("/api/reviews/<int:rid>/request-changes")
@authed
def r_review_changes(c, user, rid):
    return core.request_changes(c, user, rid, body())


@app.get("/api/reviews/<int:rid>/approval-record.pdf")
@authed
def r_review_pdf(c, user, rid):
    data = core.approval_record_pdf(c, user, rid)
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=approval-record-{rid}.pdf"})


@app.get("/api/uploads/<name>")
@authed
def r_upload(c, user, name):
    if name != os.path.basename(name) or not c.execute(
            "SELECT 1 FROM review_versions v JOIN reviews r ON r.id=v.review_id WHERE v.image_path=? AND r.workspace_id=?",
            (name, user["workspace_id"])).fetchone():
        raise core.Err(404, "Not found.")
    return send_from_directory(db.UPLOAD_DIR, name)


@app.post("/api/findings/<int:fid>/accept")
@authed
def r_f_accept(c, user, fid):
    return core.accept_finding(c, user, fid)


@app.post("/api/findings/<int:fid>/edit")
@authed
def r_f_edit(c, user, fid):
    d = body()
    if not isinstance(d.get("text"), str):
        raise core.Err(400, "Enter the replacement text.")
    return core.accept_finding(c, user, fid, custom=d["text"])


@app.post("/api/findings/<int:fid>/dismiss")
@authed
def r_f_dismiss(c, user, fid):
    return core.dismiss_finding(c, user, fid, body())


@app.post("/api/findings/<int:fid>/escalate")
@authed
def r_f_escalate(c, user, fid):
    return core.escalate_finding(c, user, fid, body())


@app.post("/api/findings/<int:fid>/clear")
@authed
def r_f_clear(c, user, fid):
    return core.clear_finding(c, user, fid, body())


@app.post("/api/findings/<int:fid>/override")
@authed
def r_f_override(c, user, fid):
    return core.override_finding(c, user, fid, body())


@app.post("/api/comments")
@authed
def r_comment(c, user):
    return core.add_comment(c, user, body())


# ---------------------------------------------------------------- settings
@app.get("/api/settings/users")
@authed
def r_users(c, user):
    return core.list_users(c, user)


@app.post("/api/settings/users")
@authed
def r_user_invite(c, user):
    return core.invite_user(c, user, body())


@app.put("/api/settings/users/<int:uid>")
@authed
def r_user_role(c, user, uid):
    return core.change_role(c, user, uid, body())


@app.delete("/api/settings/users/<int:uid>")
@authed
def r_user_remove(c, user, uid):
    return core.remove_user(c, user, uid)


@app.get("/api/settings/ai")
@authed
def r_ai_get(c, user):
    return core.ai_settings(c, user)


@app.put("/api/settings/ai")
@authed
def r_ai_set(c, user):
    return core.set_ai(c, user, body())


@app.get("/api/audit")
@authed
def r_audit(c, user):
    return core.audit_list(c, user, request.args.get("user", type=int))


# ---------------------------------------------------------------- frontend
@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/<path:path>")
def static_files(path):
    full = os.path.join(FRONTEND, path)
    if os.path.isfile(full):
        return send_from_directory(FRONTEND, path)
    return send_from_directory(FRONTEND, "index.html")


def create_app():
    db.init()
    if os.environ.get("BRANDSURE_DEMO", "1") != "0":
        from . import seed
        with db.get_db() as c:
            if not c.execute("SELECT 1 FROM workspaces LIMIT 1").fetchone():
                seed.load(c)
    return app
