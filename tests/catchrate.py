"""Catch-rate test: sample drafts with the findings we EXPECT, run through the real engine.

Run:  python tests/catchrate.py            (prints a report)
      python tests/catchrate.py --write    (also writes docs/TEST_RESULTS.md)

Each case lists expected findings as (source_code, text that must be inside the flagged quote).
"Clean" cases expect NO findings (false-positive check). "AI-only" cases are things a rule
cannot see (jargon, named competitors); they are reported separately and are expected to be
MISSED when the AI step is off.
"""
import os
import sys
import tempfile

os.environ["BRANDSURE_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import core, db, engine, seed  # noqa: E402

# Codes come from backend/seed.py (G1.. guidelines, T glossary, F facts, C claims, B colours)
RULE_CASES = [
    # id, text, [(code, must-be-in-quote)], note
    ("R01", "The Nova app supports 12 languages.", [("F1", "12")], "wrong number: languages"),
    ("R02", "Nova Foods ships to 15 countries.", [("F2", "15")], "wrong number: countries"),
    ("R03", "Each NovaPack has 20 g of protein per serving.", [("F3", "20")], "wrong number: protein"),
    ("R04", "Nova Foods was founded in 2015.", [("F4", "2015")], "wrong number: year"),
    ("R05", "Delivery is free on orders above 299 rupees.", [("F5", "299")], "wrong number: delivery"),
    ("R06", "We are the fastest snack brand around.", [("C1", "fastest")], "forbidden claim"),
    ("R07", "Guaranteed to make your day better.", [("C4", "uaranteed")], "forbidden claim"),
    ("R08", "Try our best snack today.", [("C2", "best")], "needs-proof claim"),
    ("R09", "Made with 100% natural ingredients.", [("C3", "100% natural")], "needs-proof claim"),
    ("R10", "Try the new Nova Pack today.", [("T1", "Nova Pack")], "glossary: product name"),
    ("R11", "Welcome to NovaFoods, where snacks are made with care.", [("T2", "NovaFoods")], "glossary: company name"),
    ("R12", "Our vegan-ish snacks are ready for you.", [("T3", "vegan-ish")], "glossary: dietary term"),
    ("R13", "Big news is coming your way soon!!!", [("G3", "!!!")], "style: repeated exclamation"),
    ("R14", "This is a HUGE launch for you and your family.", [("G4", "HUGE")], "style: ALL CAPS"),
    ("R15", "Our new snack range is made with simple ingredients that you already know and trust, and it is packed in "
            "bags that are easy to carry in your pocket, your desk drawer or your gym bag every single day.",
     [("G5", "Our new snack range")], "style: sentence over 25 words"),
    ("R16", "Our app is the fastest in India and now supports 12 languages!!!",
     [("C1", "fastest"), ("F1", "12"), ("G3", "!!!")], "the 3-minute demo draft (three findings)"),
    ("R17", "We make the cheapest snacks in town.", [("NONE", "cheapest")], "superlative with no approved source"),
    ("R18", "Join us today. NovaPack is ready, and the Nova app now supports 12 languages, so you can read it your way.",
     [("F1", "12")], "wrong number inside a longer text"),
]
CLEAN_CASES = [
    ("K01", "The Nova app supports 9 languages.", "correct number must not be flagged"),
    ("K02", "Nova Foods was founded in 2019 and ships to 9 countries.", "two correct facts"),
    ("K03", "Meet NovaPack. A plant-based snack with 12 g of protein.", "approved term and correct fact"),
    ("K04", "Delivery is free on orders above 499 rupees.", "correct fact"),
]
# (id, image dict, [(code, must-be-in-quote)], note). Codes B1..B5 are colours, B5 = minimum logo width.
IMAGE_CASES = [
    ("I01", {"alt": "A bag of NovaPack", "text_color": "#CCCCCC", "bg_color": "#FFFFFF"}, [("G9", "#CCCCCC")], "low contrast"),
    ("I02", {"alt": "", "text_color": "#222222", "bg_color": "#F6F1E7"}, [("G8", "Alt text")], "missing alt text"),
    ("I03", {"alt": "NovaPack", "text_color": "#222222", "bg_color": "#F6F1E7", "logo_width": 80}, [("B5", "80")], "logo too small"),
    ("I04", {"alt": "NovaPack", "text_color": "#222222", "bg_color": "#F6F1E7", "logo_width": 200}, [], "clean image"),
]
AI_ONLY_CASES = [
    ("A01", "At Nova Foods we leverage synergy across teams to delight you.", [("G2", "leverage")], "jargon (needs AI)"),
    ("A02", "NovaPack tastes better than Acme Snacks every time.", [("G7", "Acme")], "named competitor (needs AI)"),
]


def load_items():
    db.init()
    with db.get_db() as c:
        seed.load(c)
        ws = c.execute("SELECT id FROM workspaces").fetchone()[0]
        ver = c.execute("SELECT MAX(number) FROM knowledge_versions WHERE workspace_id=?", (ws,)).fetchone()[0]
        return core.items_for_version(c, ws, ver)


def hit(findings, code, frag):
    return any(f["source_code"] == code and frag.lower() in f["quote"].lower() for f in findings)


def main():
    items = load_items()
    lines, caught, expected_total, rows = [], 0, 0, []
    for cid, text, exp, note in RULE_CASES:
        f, _ = engine.run_checks(text, items, allow_ai=False)
        got = [hit(f, code, frag) for code, frag in exp]
        extra = [x for x in f if not any(x["source_code"] == code and frag.lower() in x["quote"].lower() for code, frag in exp)]
        caught += sum(got)
        expected_total += len(exp)
        rows.append((cid, note, f"{sum(got)}/{len(exp)}", "PASS" if all(got) else "MISS",
                     ", ".join(f"{x['source_code']}:{x['quote'][:18]!r}" for x in extra) or "-"))
    for cid, img, exp, note in IMAGE_CASES:
        f, _ = engine.run_checks("", items, allow_ai=False, image=img)
        got = [hit(f, code, frag) for code, frag in exp]
        extra = [x for x in f if not any(x["source_code"] == code and frag.lower() in x["quote"].lower() for code, frag in exp)]
        caught += sum(got)
        expected_total += len(exp)
        ok = all(got) and (exp or not f)
        rows.append((cid, note, f"{sum(got)}/{len(exp)}", "PASS" if ok else "MISS",
                     ", ".join(f"{x['source_code']}:{x['quote'][:18]!r}" for x in extra) or "-"))
    fp = 0
    for cid, text, note in CLEAN_CASES:
        f, _ = engine.run_checks(text, items, allow_ai=False)
        fp += len(f)
        rows.append((cid, note, "0 expected", "PASS" if not f else "FALSE POSITIVE",
                     ", ".join(f"{x['source_code']}:{x['quote'][:18]!r}" for x in f) or "-"))
    ai_rows, ai_caught = [], 0
    for cid, text, exp, note in AI_ONLY_CASES:
        f, _ = engine.run_checks(text, items, allow_ai=False)
        got = all(hit(f, code, frag) for code, frag in exp)
        ai_caught += got
        ai_rows.append((cid, note, "caught by rules" if got else "not caught by rules (needs AI step)"))

    rule_cases = len(RULE_CASES) + len(IMAGE_CASES)
    passed = sum(1 for r in rows if r[3] == "PASS")
    out = ["# BrandSure test results (rule-based engine, AI off)", "",
           f"- Expected findings caught: **{caught} of {expected_total}**",
           f"- Cases passed: **{passed} of {len(rows)}** ({rule_cases} with expected findings, {len(CLEAN_CASES)} clean drafts)",
           f"- False positives on clean drafts: **{fp}**",
           f"- AI-only cases (jargon, named competitors) caught by rules alone: {ai_caught} of {len(AI_ONLY_CASES)}",
           "", "Reproduce: `python tests/catchrate.py --write`", "",
           "| Case | What it tests | Expected found | Result | Extra findings |", "|---|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    out += ["", "## Needs the AI step", "", "| Case | What it tests | Rule-only result |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in ai_rows]
    out += ["", "These two are judgement calls a rule cannot make. They are the reason the optional AI check exists; "
            "its citations are re-verified in code (see `tests/test_flow.py::test_ai_citations_are_verified`)."]
    text = "\n".join(out)
    print(text)
    if "--write" in sys.argv:
        docs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
        os.makedirs(docs, exist_ok=True)
        with open(os.path.join(docs, "TEST_RESULTS.md"), "w") as fh:
            fh.write(text + "\n")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
