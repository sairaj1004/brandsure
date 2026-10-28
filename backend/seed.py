"""Demo data: a fictional company called Nova Foods, four users and a few sample reviews."""
from . import core, db

DEMO_PASSWORD = "demo1234"

USERS = [
    ("Asha Admin", "admin@nova.test", "admin"),
    ("Manoj Manager", "manager@nova.test", "manager"),
    ("Riya Reviewer", "reviewer@nova.test", "reviewer"),
    ("Chetan Creator", "creator@nova.test", "creator"),
]

# kind, title, body, severity, category, value, source, extra
KNOWLEDGE = [
    ("guideline", "Voice", "Write in a warm, plain, confident voice. Prefer short words and speak to the reader as 'you'.", "Medium", "Tone", "", "", ""),
    ("guideline", "No jargon", "Do not use corporate jargon such as 'synergy' or 'leverage' in customer copy.", "Low", "Tone", "", "", ""),
    ("guideline", "Exclamation marks", "Use at most one exclamation mark per piece and never repeat it.", "Low", "Tone", "1", "", "max_exclaim"),
    ("guideline", "No shouting", "Avoid words in ALL CAPS except approved acronyms.", "Low", "Tone", "", "", "no_caps"),
    ("guideline", "Sentence length", "Keep sentences under 25 words.", "Low", "Tone", "25", "", "max_sentence"),
    ("guideline", "Easy reading", "Aim for a reading-ease score of at least 50.", "Low", "Tone", "50", "", "min_readability"),
    ("guideline", "No named competitors", "Never compare Nova Foods with a named competitor.", "High", "Messaging", "", "", ""),
    ("guideline", "Alt text", "Every image needs alt text that describes what it shows.", "Medium", "Accessibility", "", "", "alt_required"),
    ("guideline", "Contrast", "Text must have a contrast ratio of at least 4.5 to 1 against its background.", "High", "Accessibility", "4.5", "", "min_contrast"),
    ("glossary", "NovaPack", "Nova Pack, novapack, Nova-pack", "Medium", "", "", "Product name is one word with capitals N and P.", ""),
    ("glossary", "Nova Foods", "NovaFoods, Nova foods", "Medium", "", "", "Company name is two words.", ""),
    ("glossary", "plant-based", "vegan-ish, meatless", "Medium", "", "", "Use the approved dietary term.", ""),
    ("fact", "The Nova app supports 9 languages.", "", "High", "languages,language", "9", "Product sheet 2026", "2026-09-01"),
    ("fact", "Nova Foods ships to 9 countries.", "", "High", "countries,country", "9", "Operations report", "2026-08-15"),
    ("fact", "NovaPack has 12 g of protein per serving.", "", "High", "protein", "12", "Nutrition label", "2026-07-01"),
    ("fact", "Nova Foods was founded in 2019.", "", "Medium", "founded", "2019", "Company registry", "2026-01-10"),
    ("fact", "Delivery is free on orders above 499 rupees.", "", "High", "delivery", "499", "Pricing policy", "2026-09-20"),
    ("claim", "fastest", "", "High", "", "built for speed", "", "Forbidden"),
    ("claim", "best", "", "Medium", "", "loved by our customers", "", "Needs proof"),
    ("claim", "100% natural", "", "Medium", "", "made with natural ingredients", "Lab report LR-22", "Needs proof"),
    ("claim", "guaranteed", "", "High", "", "backed by our quality promise", "", "Forbidden"),
    ("claim", "plant-based", "", "Low", "", "", "", "Allowed"),
    ("colour", "Nova Green", "", "Medium", "", "#1B7F5C", "", ""),
    ("colour", "Cream", "", "Medium", "", "#F6F1E7", "", ""),
    ("colour", "Charcoal", "", "Medium", "", "#222222", "", ""),
    ("colour", "Harvest Orange", "", "Medium", "", "#F28C28", "", ""),
    ("colour", "Minimum logo width", "Logo must be at least this wide (px).", "Medium", "", "120", "", "min_logo"),
]

REVIEWS = [
    # title, channel, audience, text, creator index, actions
    ("Summer sale post", "Social post", "Customers",
     "Our NovaPack is the best snack in India!!! Now with 12 g of protein, free delivery on every order and a world-class taste. Grab one for the office, one for the gym bag and one for the long weekend trip, because every single pack is made to travel well wherever your day takes you.", "creator"),
    ("Careers page intro", "Web page", "Students",
     "At Nova Foods we leverage synergy across teams to deliver value. Join our mission to make plant-based food for everyone, and enjoy an environment where learning never stops and every voice is heard by everyone around you every single day.", "creator"),
    ("App update email", "Email", "Customers",
     "The Nova app now supports 12 languages. Update today to try it.", "creator"),
]


def load(c):
    wid = c.execute("INSERT INTO workspaces(name,created_at) VALUES(?,?)", ("Nova Foods (demo)", db.now())).lastrowid
    users = {}
    for name, email, role in USERS:
        uid = c.execute("INSERT INTO users(workspace_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                        (wid, name, email, db.hash_pw(DEMO_PASSWORD), role, db.now())).lastrowid
        users[role] = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    mgr = users["manager"]
    for kind, title, body, sev, cat, value, source, extra in KNOWLEDGE:
        core.save_knowledge(c, mgr, {"kind": kind, "title": title, "body": body, "severity": sev, "category": cat,
                                     "value": value, "source": source, "extra": extra, "status": "active"})
    core.publish_version(c, mgr)
    creator = users["creator"]
    ids = []
    for title, channel, audience, text, _ in REVIEWS:
        r = core.create_review(c, creator, {"title": title, "channel": channel, "audience": audience,
                                            "content_type": "text", "content_text": text})
        ids.append(r["id"])
    # sample history so the Insights page is not empty
    for rid in ids[:2]:
        v = core._latest_version(c, rid)
        for f in c.execute("SELECT id, source_code FROM findings WHERE review_version_id=? AND source_code IN (SELECT code FROM knowledge_items WHERE extra IN ('max_sentence','min_readability'))", (v["id"],)).fetchall():
            core.dismiss_finding(c, creator, f["id"], {"reason": "Rule is unclear", "note": "Not sure what counts as too long."})
    # one finished approval so 'Recently approved' and review speed have data
    rid = ids[2]
    v = core._latest_version(c, rid)
    for f in c.execute("SELECT id FROM findings WHERE review_version_id=? AND state='open'", (v["id"],)).fetchall():
        try:
            core.accept_finding(c, creator, f["id"])
        except core.Err:
            pass
        break
    core.submit_review(c, creator, rid)
    core.approve_review(c, users["reviewer"], rid, {"note": "Looks good."})
