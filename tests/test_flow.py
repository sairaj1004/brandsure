"""End-to-end tests of the API using Flask's test client. Run: python -m unittest discover -s tests -v"""
import os, shutil, tempfile, unittest, base64

os.environ["BRANDSURE_DATA"] = tempfile.mkdtemp()
os.environ.pop("ANTHROPIC_API_KEY", None)
from backend import app as appmod, core, engine, db  # noqa: E402

DEMO = "demo1234"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = appmod.create_app()
        cls.cl = cls.app.test_client()

    def login(self, who):
        r = self.cl.post("/api/auth/login", json={"email": f"{who}@nova.test", "password": DEMO})
        self.assertEqual(r.status_code, 200, r.get_data())
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def call(self, method, path, who, json=None, status=200):
        r = getattr(self.cl, method)(path, json=json, headers=self.login(who))
        self.assertEqual(r.status_code, status, f"{method} {path} -> {r.status_code} {r.get_data()[:300]}")
        return r.get_json() if r.mimetype == "application/json" else r.get_data()


class TestAuth(Base):
    def test_bad_login(self):
        r = self.cl.post("/api/auth/login", json={"email": "manager@nova.test", "password": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_no_token(self):
        self.assertEqual(self.cl.get("/api/dashboard").status_code, 401)

    def test_register_makes_admin(self):
        r = self.cl.post("/api/auth/register", json={"workspace_name": "Acme", "name": "Zed", "email": "zed@acme.test", "password": "longenough1"})
        self.assertEqual(r.get_json()["user"]["role"], "admin")
        dup = self.cl.post("/api/auth/register", json={"workspace_name": "Acme", "name": "Zed", "email": "zed@acme.test", "password": "longenough1"})
        self.assertEqual(dup.status_code, 409)

    def test_workspace_isolation(self):
        r = self.cl.post("/api/auth/register", json={"workspace_name": "Other", "name": "Ann", "email": "ann@other.test", "password": "longenough1"})
        h = {"Authorization": "Bearer " + r.get_json()["token"]}
        self.assertEqual(self.cl.get("/api/reviews/1", headers=h).status_code, 404)
        self.assertEqual(self.cl.get("/api/knowledge", headers=h).get_json()["items"], [])


class TestEngine(unittest.TestCase):
    def items(self):
        with db.get_db() as c:
            return core.items_for_version(c, 1, 1)

    def test_demo_text(self):
        f, checks = engine.run_checks("Our app is the fastest in India and now supports 12 languages!!!", self.items())
        by = {x["quote"]: x for x in f}
        self.assertEqual(by["the fastest"]["severity"], "High")
        self.assertEqual(by["the fastest"]["suggestion"], "built for speed")
        self.assertEqual(by["12"]["verdict"], "contradicted")
        self.assertEqual(by["12"]["suggestion"], "9")
        self.assertEqual(by["12"]["source_code"], "F1")
        self.assertIn("!!!", by)

    def test_supported_number_not_flagged(self):
        f, _ = engine.run_checks("The Nova app supports 9 languages.", self.items())
        self.assertEqual([x for x in f if x["type"] == "Claim"], [])

    def test_terminology_keeps_capital(self):
        f, _ = engine.run_checks("Try Nova Pack today.", self.items())
        self.assertEqual(f[0]["suggestion"], "NovaPack")

    def test_unverified_superlative_has_no_source(self):
        f, _ = engine.run_checks("We are the cheapest around.", self.items())
        self.assertEqual(f[0]["source_code"], "NONE")
        self.assertEqual(f[0]["verdict"], "unverified")

    def test_ai_skipped_when_confidential(self):
        called = []
        _, checks = engine.run_checks("Hello there.", self.items(), confidential=True, ai_fn=lambda p: called.append(p) or "{}")
        self.assertEqual(called, [])
        ai = [c for c in checks if c["check_type"] == "ai"][0]
        self.assertEqual(ai["status"], "skipped")

    def test_ai_citations_are_verified(self):
        items = self.items()
        text = "We ship worldwide in 3 days and we sound very stuffy indeed."
        fake = ('{"findings":['
                '{"type":"claim","quote":"worldwide","source_id":"F2","source_quote":"ships to 9 countries","verdict":"contradicted","why":"x","suggestion":"to 9 countries","confidence":"high"},'
                '{"type":"claim","quote":"in 3 days","source_id":"F999","source_quote":"made up","verdict":"supported","why":"x","suggestion":"","confidence":"high"},'
                '{"type":"tone","quote":"very stuffy","source_id":"G999","source_quote":"nothing","verdict":"violation","why":"x","suggestion":"","confidence":"high"},'
                '{"type":"tone","quote":"not in the draft","source_id":"G1","source_quote":"warm","verdict":"violation","why":"x","suggestion":"","confidence":"high"}]}')
        f, checks = engine.run_checks(text, items, ai_fn=lambda p: fake)
        ai = [x for x in f if x["check_type"] == "ai"]
        quotes = {x["quote"]: x for x in ai}
        self.assertEqual(quotes["worldwide"]["source_code"], "F2")           # real citation kept
        self.assertEqual(quotes["in 3 days"]["verdict"], "unverified")       # fake citation downgraded
        self.assertEqual(quotes["in 3 days"]["source_code"], "NONE")
        self.assertNotIn("very stuffy", quotes)                              # tone with fake guideline rejected
        self.assertNotIn("not in the draft", quotes)                         # quote not in draft rejected

    def test_ai_failure_does_not_block(self):
        def boom(p): raise RuntimeError("timeout")
        f, checks = engine.run_checks("Try Nova Pack.", self.items(), ai_fn=boom)
        self.assertTrue(f)
        self.assertEqual([c for c in checks if c["check_type"] == "ai"][0]["status"], "failed")

    def test_image_checks(self):
        f, checks = engine.run_checks("", self.items(), image={"alt": "", "text_color": "#CCCCCC", "bg_color": "#FFFFFF", "logo_width": 80})
        types = {x["quote"].split(" ")[0] for x in f}
        self.assertIn("Alt", types)
        self.assertTrue(any(x["type"] == "Accessibility" and x["severity"] == "High" for x in f))
        self.assertTrue(any(x["quote"].startswith("Logo width") for x in f))

    def test_contrast_math(self):
        self.assertAlmostEqual(engine.contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=1)


class TestWorkflow(Base):
    def make(self, text, who="creator", **extra):
        d = {"title": "T", "channel": "Social post", "audience": "Customers", "content_type": "text", "content_text": text, **extra}
        return self.call("post", "/api/reviews", who, d)["id"]

    def test_full_loop(self):
        rid = self.make("Our app is the fastest in India and now supports 12 languages!!!")
        rep = self.call("get", f"/api/reviews/{rid}", "creator")
        self.assertEqual(rep["review"]["status"], "checked")
        self.assertGreaterEqual(rep["unresolved_high"], 2)
        # cannot submit with open High findings
        self.call("post", f"/api/reviews/{rid}/submit", "creator", status=400)
        highs = [f for f in rep["findings"] if f["severity"] == "High"]
        # accept fix on the first high; a new version appears
        r = self.call("post", f"/api/findings/{highs[0]['id']}/accept", "creator")
        self.assertEqual(r["version"], 2)
        rep = self.call("get", f"/api/reviews/{rid}", "creator")
        self.assertEqual(rep["version"]["number"], 2)
        # dismiss needs a valid reason
        high = [f for f in rep["findings"] if f["severity"] == "High"][0]
        self.call("post", f"/api/findings/{high['id']}/dismiss", "creator", {"reason": "nope"}, status=400)
        self.call("post", f"/api/findings/{high['id']}/dismiss", "creator", {"reason": "Approved exception"})
        # old finding on old version cannot be acted on
        self.call("post", f"/api/findings/{highs[0]['id']}/accept", "creator", status=409)
        # reviewer cannot edit content
        self.call("post", f"/api/reviews/{rid}/versions", "reviewer", {"content_text": "x"}, status=403)
        self.call("post", f"/api/reviews/{rid}/submit", "creator")
        # creator cannot approve
        self.call("post", f"/api/reviews/{rid}/approve", "creator", {}, status=403)
        # request changes needs a note
        self.call("post", f"/api/reviews/{rid}/request-changes", "reviewer", {}, status=400)
        self.call("post", f"/api/reviews/{rid}/request-changes", "reviewer", {"note": "Please recheck tone."})
        self.assertEqual(self.call("get", f"/api/reviews/{rid}", "creator")["review"]["status"], "changes_requested")
        self.call("post", f"/api/reviews/{rid}/submit", "creator")
        self.call("post", f"/api/reviews/{rid}/approve", "reviewer", {})
        rep = self.call("get", f"/api/reviews/{rid}", "creator")
        self.assertEqual(rep["review"]["status"], "approved")
        # approved review is locked
        self.call("post", f"/api/reviews/{rid}/versions", "creator", {"content_text": "changed"}, status=409)
        pdf = self.call("get", f"/api/reviews/{rid}/approval-record.pdf", "manager")
        self.assertTrue(pdf.startswith(b"%PDF"))
        # history lists the steps
        actions = [h["action"] for h in rep["history"]]
        for a in ("review_create", "finding_accept", "finding_dismiss", "review_submit", "review_approve", "review_request_changes"):
            self.assertIn(a, actions)

    def test_override_and_reviewer_block(self):
        rid = self.make("We are the fastest. Truly guaranteed results.")
        # manager overrides each High finding with a justification, then creator can submit
        rep = self.call("get", f"/api/reviews/{rid}", "creator")
        for f in [f for f in rep["findings"] if f["severity"] == "High"]:
            self.call("post", f"/api/findings/{f['id']}/override", "creator", {"justification": "x"}, status=403)
            self.call("post", f"/api/findings/{f['id']}/override", "manager", {}, status=400)
            self.call("post", f"/api/findings/{f['id']}/override", "manager", {"justification": "Legal approved wording"})
        self.call("post", f"/api/reviews/{rid}/submit", "creator")
        self.call("post", f"/api/reviews/{rid}/approve", "reviewer", {})

    def test_escalate_and_clear(self):
        rid = self.make("We are the cheapest around.")
        rep = self.call("get", f"/api/reviews/{rid}", "creator")
        f = rep["findings"][0]
        revs = self.call("get", "/api/reviewers", "creator")
        rv = [r for r in revs if r["role"] == "reviewer"][0]
        self.call("post", f"/api/findings/{f['id']}/escalate", "creator", {"reviewer_id": rv["id"], "note": "check"})
        dash = self.call("get", "/api/dashboard", "reviewer")
        self.assertIn(rid, [r["id"] for r in dash["action"]])
        self.call("post", f"/api/findings/{f['id']}/clear", "reviewer", {}, status=400)
        self.call("post", f"/api/findings/{f['id']}/clear", "reviewer", {"note": "Proof seen"})

    def test_approve_high_open_requires_manager(self):
        rid = self.make("Plain safe text with no problems at all here.")
        self.call("post", f"/api/reviews/{rid}/submit", "creator")
        self.call("post", f"/api/reviews/{rid}/approve", "manager", {})

    def test_confidential_runs_no_ai(self):
        rid = self.make("Our secret launch is coming.", confidential=True)
        rep = self.call("get", f"/api/reviews/{rid}", "creator")
        ai = [c for c in rep["checks"] if c["check_type"] == "ai"][0]
        self.assertEqual(ai["status"], "skipped")
        self.assertIn("Confidential", ai["message"])

    def test_diff(self):
        rid = self.make("Try Nova Pack today.")
        self.call("post", f"/api/reviews/{rid}/versions", "creator", {"content_text": "Try NovaPack today."})
        d = self.call("get", f"/api/reviews/{rid}/diff?a=1&b=2", "creator")
        kinds = {o["t"] for o in d["ops"]}
        self.assertTrue({"del", "ins"} <= kinds)

    def test_validation(self):
        self.call("post", "/api/reviews", "creator", {"title": "", "channel": "Email", "audience": "Customers", "content_text": "x"}, status=400)
        self.call("post", "/api/reviews", "creator", {"title": "a", "channel": "Bad", "audience": "Customers", "content_text": "x"}, status=400)
        self.call("post", "/api/reviews", "creator", {"title": "a", "channel": "Email", "audience": "Customers", "content_text": "  "}, status=400)

    def test_image_review(self):
        png = base64.b64encode(bytes.fromhex("89504e470d0a1a0a")).decode()
        r = self.call("post", "/api/reviews", "creator", {"title": "Banner", "channel": "Social post", "audience": "Customers",
                      "content_type": "image", "image_b64": png, "image_name": "a.png", "alt_text": "", "caption": "Fresh and natural",
                      "text_color": "#CCCCCC", "bg_color": "#FFFFFF", "logo_width": 60})
        rep = self.call("get", f"/api/reviews/{r['id']}", "creator")
        quotes = [f["quote"] for f in rep["findings"]]
        self.assertIn("Alt text", quotes)
        img = self.cl.get("/api/uploads/" + rep["version"]["image_path"], headers=self.login("creator"))
        self.assertEqual(img.status_code, 200)
        self.call("post", "/api/reviews", "creator", {"title": "x", "channel": "Email", "audience": "Customers", "content_type": "image",
                  "image_b64": png, "image_name": "evil.html"}, status=400)


class TestKnowledgeAndSettings(Base):
    def test_creator_cannot_edit_knowledge(self):
        self.call("post", "/api/knowledge", "creator", {"kind": "fact", "title": "x"}, status=403)
        self.call("post", "/api/knowledge/publish", "creator", status=403)

    def test_add_edit_archive_publish(self):
        it = self.call("post", "/api/knowledge", "manager", {"kind": "glossary", "title": "Zestify", "body": "zestyfy"})
        self.assertTrue(it["code"].startswith("T"))
        self.call("put", f"/api/knowledge/{it['id']}", "manager", {"body": "zestyfy, zestifi"})
        v = self.call("post", "/api/knowledge/publish", "manager")
        self.assertGreaterEqual(v["version"], 2)
        self.call("post", f"/api/knowledge/{it['id']}/archive", "manager")

    def test_import_preview(self):
        data = base64.b64encode(b"1. Always write in plain language for readers.\n2. Never promise results you cannot prove.\nshort").decode()
        r = self.call("post", "/api/knowledge/import", "manager", {"filename": "rules.md", "data_b64": data})
        self.assertEqual(len(r["rules"]), 2)
        self.call("post", "/api/knowledge/import", "manager", {"filename": "rules.exe", "data_b64": data}, status=400)

    def test_insights(self):
        r = self.call("get", "/api/insights", "manager")
        self.assertTrue(r["top"])
        self.assertTrue(any(u["code"] for u in r["unclear"]))
        self.call("get", "/api/insights", "creator", status=403)

    def test_ai_switch_and_audit(self):
        self.call("put", "/api/settings/ai", "manager", {"allow_ai": False}, status=403)
        r = self.call("put", "/api/settings/ai", "admin", {"allow_ai": False})
        self.assertFalse(r["allow_ai"])
        self.call("put", "/api/settings/ai", "admin", {"allow_ai": True})
        log = self.call("get", "/api/audit", "admin")["rows"]
        self.assertTrue(any(x["action"] == "settings_ai" for x in log))

    def test_user_management(self):
        r = self.call("post", "/api/settings/users", "admin", {"name": "New Person", "email": "new@nova.test", "role": "creator"})
        self.assertTrue(r["temp_password"])
        self.call("put", f"/api/settings/users/{r['id']}", "admin", {"role": "reviewer"})
        self.call("delete", f"/api/settings/users/{r['id']}", "admin")
        users = self.call("get", "/api/settings/users", "admin")
        admin_id = [u for u in users if u["role"] == "admin"][0]["id"]
        self.call("put", f"/api/settings/users/{admin_id}", "admin", {"role": "creator"}, status=400)

    def test_approvals_roles(self):
        self.call("get", "/api/approvals?tab=waiting", "creator", status=403)
        self.assertIn("rows", self.call("get", "/api/approvals?tab=approved", "reviewer"))


if __name__ == "__main__":
    unittest.main()
