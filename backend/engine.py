"""Review engine. Pure functions: text + knowledge items in, findings + 'checks run' out.

Rule-based checks always run. The optional AI check only runs when it is allowed
(not confidential, not switched off, API key present) and every AI finding is
re-verified in code against the real source text before it is shown.
"""
import json
import os
import re
import urllib.request

SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CONF_VALUES = {"high", "medium", "low"}

SUPER = [r"fastest", r"best", r"(?<!\w)#\s?1(?!\d)", r"number one", r"no\.\s?1", r"leading",
         r"guaranteed?", r"100\s?%", r"cheapest", r"unbeatable", r"world[- ]class", r"risk[- ]free",
         r"cure[sd]?"]
SUPER_RE = re.compile(r"(?<!\w)(?:" + "|".join(SUPER) + r")(?!\w)", re.I)
SENSITIVE_RE = re.compile(r"(₹|\$|€|£|\bprice|\bdiscount|\bcure|\bhealth|\blegal|\bthan\b|\bvs\.?\b|\bcompar|\bguarantee)", re.I)
NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


# ------------------------------------------------------------------ helpers
def _check(name, ctype, status, message=""):
    return {"check_name": name, "check_type": ctype, "status": status, "message": message}


def _finding(type_, severity, quote, start, end, source_code, why, suggestion="", confidence="high",
             check_type="rule", verdict="violation", needs_reviewer=False):
    return {"type": type_, "severity": severity, "quote": quote, "start": start, "end": end,
            "source_code": source_code, "why": why, "suggestion": suggestion, "confidence": confidence,
            "check_type": check_type, "verdict": verdict, "needs_reviewer": bool(needs_reviewer)}


def sentences(text):
    """Return [(start, end, text)] for each sentence, with positions in the original text."""
    out = []
    for m in re.finditer(r"[^\n]+?(?:[.!?]+(?=\s|$)|(?=\n)|$)", text):
        s = m.group()
        stripped = s.strip()
        if not stripped:
            continue
        lead = len(s) - len(s.lstrip())
        out.append((m.start() + lead, m.start() + lead + len(stripped), stripped))
    return out


def word_re(term):
    return re.compile(r"(?<!\w)" + re.escape(term.strip()) + r"(?!\w)", re.I)


def match_case(original, replacement):
    if original[:1].isupper() and replacement[:1].islower():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def num_value(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def _num_text(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def rule_for(guidelines, key):
    for g in guidelines:
        if g.get("extra") == key:
            return g
    return None


# ------------------------------------------------------------------ colour helpers
def hex_to_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError("bad colour")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def colour_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


# ------------------------------------------------------------------ readability
def _syllables(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def flesch(text):
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 8:
        return None
    sents = max(1, len(sentences(text)))
    syl = sum(_syllables(w) for w in words)
    return 206.835 - 1.015 * len(words) / sents - 84.6 * syl / len(words)


# ------------------------------------------------------------------ rule-based checks
def check_terminology(text, glossary):
    out = []
    for g in glossary:
        preferred = g["title"].strip()
        for variant in [v.strip() for v in g["body"].split(",") if v.strip()]:
            for m in word_re(variant).finditer(text):
                if m.group() == preferred:
                    continue  # already the approved spelling
                out.append(_finding(
                    "Terminology", "Medium", m.group(), m.start(), m.end(), g["code"],
                    f'The brand glossary uses "{preferred}", not "{m.group()}".',
                    match_case(m.group(), preferred), "high"))
    return out


def check_claim_patterns(text, claims):
    out, spans = [], []
    for c in claims:
        status = (c.get("extra") or "Needs proof").strip()
        if status.lower() == "allowed":
            continue
        for m in word_re(c["title"]).finditer(text):
            spans.append((m.start(), m.end()))
            safer = (c.get("value") or "").strip()
            forbidden = status.lower() == "forbidden"
            why = (f'"{m.group()}" is a forbidden claim ({c["code"]}).' if forbidden
                   else f'"{m.group()}" needs proof before it can be published ({c["code"]}).')
            if c.get("source"):
                why += f' Proof on file: {c["source"]}.'
            q_start, q_text = m.start(), m.group()
            art = re.search(r"(?<!\w)(the|a|an)\s+$", text[:m.start()], re.I)
            if art and safer:  # replace "the fastest" as a whole so the sentence still reads correctly
                q_start, q_text = art.start(), text[art.start():m.end()]
            out.append(_finding(
                "Claim", "High" if forbidden else "Medium", q_text, q_start, m.end(), c["code"], why,
                safer, "high", "rule", "contradicted" if forbidden else "unverified",
                needs_reviewer=bool(SENSITIVE_RE.search(text[max(0, m.start() - 60):m.end() + 60]))))
    return out, spans


def check_numeric_facts(text, facts):
    """Compare numbers that sit next to a fact's topic keyword with the approved value."""
    out, stats = [], {"supported": 0, "contradicted": 0}
    all_topics = {}
    for f in facts:
        for t in f.get("category", "").split(","):
            if t.strip():
                all_topics.setdefault(t.strip().lower(), f["code"])
    for f in facts:
        approved = num_value(f.get("value", ""))
        topics = [t.strip().lower() for t in f.get("category", "").split(",") if t.strip()]
        if approved is None or not topics:
            continue
        for s_start, s_end, s_text in sentences(text):
            low = s_text.lower()
            kw_pos = None
            for t in topics:
                m = re.search(r"(?<!\w)" + re.escape(t) + r"s?(?!\w)", low)
                if m:
                    kw_pos = m.start()
                    break
            if kw_pos is None:
                continue
            best = None
            for nm in NUM_RE.finditer(s_text):
                d = abs(nm.start() - kw_pos)
                if d > 40 or (best is not None and d >= best[0]):
                    continue
                # a number that sits closer to another fact's topic belongs to that topic
                theirs = [abs(nm.start() - om.start())
                          for ot, code in all_topics.items() if code != f["code"]
                          for om in re.finditer(r"(?<!\w)" + re.escape(ot) + r"s?(?!\w)", low)]
                if theirs and min(theirs) < d:
                    continue
                best = (d, nm)
            if not best:
                continue
            nm = best[1]
            val = num_value(nm.group())
            if val is None:
                continue
            if abs(val - approved) < 1e-9:
                stats["supported"] += 1
                continue
            stats["contradicted"] += 1
            q_start = s_start + nm.start()
            out.append(_finding(
                "Claim", "High", nm.group(), q_start, q_start + len(nm.group()), f["code"],
                f'Approved fact {f["code"]} says: "{f["title"]}" (value {f["value"]}). This draft says {nm.group()}.',
                _num_text(approved), "high", "rule", "contradicted",
                needs_reviewer=bool(SENSITIVE_RE.search(s_text))))
    return out, stats


def check_unverified_superlatives(text, claim_spans):
    out = []
    for s_start, s_end, s_text in sentences(text):
        for m in SUPER_RE.finditer(s_text):
            a, b = s_start + m.start(), s_start + m.end()
            if any(a < ce and b > cs for cs, ce in claim_spans):
                continue
            out.append(_finding(
                "Claim", "Medium", m.group(), a, b, "NONE",
                f'No approved claim or fact supports "{m.group()}". Add proof to the Knowledge Base, rephrase, or ask a Reviewer.',
                "", "medium", "rule", "unverified", needs_reviewer=True))
    return out


def check_style(text, guidelines, glossary):
    out = []
    g = rule_for(guidelines, "max_exclaim")
    if g:
        limit = int(num_value(g["value"]) or 1)
        seen = 0
        for m in re.finditer(r"!+", text):
            seen += 1
            if len(m.group()) > 1 or seen > limit:
                out.append(_finding(
                    "Tone", "Low", m.group(), m.start(), m.end(), g["code"],
                    f'Use at most {limit} exclamation mark per piece and never repeat it.', ".", "high"))
    g = rule_for(guidelines, "no_caps")
    if g:
        allowed = {x["title"].upper() for x in glossary}
        for m in re.finditer(r"(?<![\w])[A-Z]{4,}(?![\w])", text):
            if m.group() in allowed:
                continue
            out.append(_finding(
                "Tone", "Low", m.group(), m.start(), m.end(), g["code"],
                "Avoid words in ALL CAPS unless they are approved acronyms.", m.group().capitalize(), "high"))
    g = rule_for(guidelines, "max_sentence")
    if g:
        limit = int(num_value(g["value"]) or 25)
        for s_start, s_end, s_text in sentences(text):
            n = len(s_text.split())
            if n > limit:
                out.append(_finding(
                    "Tone", "Low", s_text, s_start, s_end, g["code"],
                    f"This sentence has {n} words (limit {limit}). Split it into two.", "", "high"))
    g = rule_for(guidelines, "min_readability")
    if g:
        score = flesch(text)
        target = num_value(g["value"]) or 50
        if score is not None and score < target:
            out.append(_finding(
                "Tone", "Low", "Overall readability", -1, -1, g["code"],
                f"Reading-ease score is {score:.0f}; the target is at least {target:.0f}. Use shorter words and sentences.",
                "", "medium"))
    return out


def check_image(image, guidelines, colours):
    """image: dict(alt, text_color, bg_color, logo_width). Rule-based only."""
    out, checks = [], []
    g = rule_for(guidelines, "alt_required")
    if g:
        if not (image.get("alt") or "").strip():
            out.append(_finding("Accessibility", "Medium", "Alt text", -1, -1, g["code"],
                                "This image has no alt text, so screen-reader users cannot understand it.",
                                "", "high"))
        checks.append(_check("Alt text present", "rule", "ok", "Checked image alt text."))
    gc = rule_for(guidelines, "min_contrast")
    tc, bc = (image.get("text_color") or "").strip(), (image.get("bg_color") or "").strip()
    if gc and tc and bc:
        try:
            need = num_value(gc["value"]) or 4.5
            ratio = contrast_ratio(hex_to_rgb(tc), hex_to_rgb(bc))
            if ratio < need:
                out.append(_finding("Accessibility", "High", f"Text {tc} on {bc}", -1, -1, gc["code"],
                                    f"Contrast ratio is {ratio:.2f}:1; at least {need:g}:1 is required.", "", "high"))
            checks.append(_check("Colour contrast", "rule", "ok", f"Ratio {ratio:.2f}:1 (needs {need:g}:1)."))
        except ValueError:
            checks.append(_check("Colour contrast", "rule", "failed", "Could not read the colour values."))
    else:
        checks.append(_check("Colour contrast", "rule", "skipped", "No text and background colours given, or no contrast rule."))
    palette = [c for c in colours if c.get("extra") != "min_logo" and c.get("value")]
    if palette and (tc or bc):
        for label, val in (("Text colour", tc), ("Background colour", bc)):
            if not val:
                continue
            try:
                rgb = hex_to_rgb(val)
            except ValueError:
                continue
            best = min(palette, key=lambda p: colour_distance(rgb, hex_to_rgb(p["value"])))
            if colour_distance(rgb, hex_to_rgb(best["value"])) > 40:
                out.append(_finding("Visual", "Medium", f"{label} {val}", -1, -1, best["code"],
                                    f"{label} {val} is not in the brand palette. Closest brand colour: {best['title']} {best['value']}.",
                                    best["value"], "medium"))
        checks.append(_check("Brand palette match", "rule", "ok", "Compared colours with the palette."))
    else:
        checks.append(_check("Brand palette match", "rule", "skipped", "No palette in the Knowledge Base or no colours given."))
    ml = next((c for c in colours if c.get("extra") == "min_logo"), None)
    lw = int(image.get("logo_width") or 0)
    if ml and lw:
        need = int(num_value(ml["value"]) or 0)
        if lw < need:
            out.append(_finding("Visual", "Medium", f"Logo width {lw}px", -1, -1, ml["code"],
                                f"The logo is {lw}px wide; the minimum is {need}px.", str(need), "high"))
        checks.append(_check("Logo size", "rule", "ok", f"Logo {lw}px (minimum {need}px)."))
    else:
        checks.append(_check("Logo size", "rule", "skipped", "No logo width given or no minimum rule."))
    return out, checks


# ------------------------------------------------------------------ AI check (optional)
AI_SYSTEM = ("You are a brand-governance reviewer. Use ONLY the provided sources. Never invent facts. "
             "Keep the author's meaning. If unsure, use verdict 'unverified'. Return JSON only.")


def build_prompt(text, items):
    lines = []
    for it in items:
        if it.get("confidential"):
            continue
        body = it["body"] or it["title"]
        lines.append(f'[{it["code"]}] ({it["kind"]}{", " + it["category"] if it["category"] else ""}) '
                     f'{it["title"]}: {body} {("value=" + it["value"]) if it["value"] else ""}'.strip())
    return ("SOURCES:\n" + "\n".join(lines[:60]) + "\n\nDRAFT:\n" + text +
            '\n\nReturn {"findings":[{"type":"claim|tone|terminology","quote":"exact words from the draft",'
            '"source_id":"G1 or F2 or C3","source_quote":"exact words from that source",'
            '"verdict":"supported|contradicted|unverified|violation","why":"one or two plain sentences",'
            '"suggestion":"replacement text that keeps the author\'s meaning","confidence":"high|medium|low"}]}. '
            "Only list problems (not supported claims). JSON only.")


def anthropic_ai(prompt):
    key = os.environ["ANTHROPIC_API_KEY"]
    body = json.dumps({"model": os.environ.get("BRANDSURE_MODEL", "claude-sonnet-5-5"), "max_tokens": 1500,
                       "system": AI_SYSTEM, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return "".join(b.get("text", "") for b in data.get("content", []))


def default_ai_fn():
    return anthropic_ai if os.environ.get("ANTHROPIC_API_KEY") else None


def parse_ai_json(raw):
    a, b = raw.find("{"), raw.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("no JSON in AI reply")
    return json.loads(raw[a:b + 1]).get("findings", [])


def validate_ai_findings(raw_findings, text, items):
    """Never trust the model: keep a finding only if its quote is in the draft and its
    citation is real. Claims with a fake citation are downgraded to 'unverified'."""
    by_code = {i["code"]: i for i in items if not i.get("confidential")}
    out = []
    for f in raw_findings if isinstance(raw_findings, list) else []:
        if not isinstance(f, dict):
            continue
        quote = str(f.get("quote", ""))
        pos = text.lower().find(quote.lower()) if quote else -1
        if pos < 0:
            continue
        item = by_code.get(str(f.get("source_id", "")))
        sq = str(f.get("source_quote", "")).strip().lower()
        hay = (item["title"] + " " + item["body"] + " " + item["value"]).lower() if item else ""
        cited_ok = bool(item and sq and sq in hay)
        ftype = str(f.get("type", "tone")).lower()
        conf = str(f.get("confidence", "medium")).lower()
        conf = conf if conf in CONF_VALUES else "medium"
        verdict = str(f.get("verdict", "violation")).lower()
        if ftype == "claim":
            if not cited_ok:
                verdict, code, sev = "unverified", "NONE", "Medium"
            else:
                code = item["code"]
                verdict = verdict if verdict in ("supported", "contradicted", "unverified") else "unverified"
                if verdict == "supported":
                    continue
                sev = "High" if verdict == "contradicted" else "Medium"
            label = "Claim"
        else:
            if not cited_ok:
                continue  # tone/terminology findings without a real guideline are rejected
            code, verdict = item["code"], "violation"
            sev = item["severity"] if item["severity"] in SEV_ORDER else "Medium"
            label = "Terminology" if ftype == "terminology" else "Tone"
        out.append(_finding(label, sev, text[pos:pos + len(quote)], pos, pos + len(quote), code,
                            str(f.get("why", ""))[:400], str(f.get("suggestion", ""))[:400], conf, "ai", verdict,
                            needs_reviewer=(label == "Claim" and (verdict != "supported") and bool(SENSITIVE_RE.search(text)))))
    return out


# ------------------------------------------------------------------ main entry
def run_checks(text, items, confidential=False, allow_ai=True, image=None, ai_fn=None):
    """Return (findings, checks). `items` are active knowledge items (dicts)."""
    guidelines = [i for i in items if i["kind"] == "guideline"]
    glossary = [i for i in items if i["kind"] == "glossary"]
    facts = [i for i in items if i["kind"] == "fact"]
    claims = [i for i in items if i["kind"] == "claim"]
    colours = [i for i in items if i["kind"] == "colour"]
    findings, checks = [], []

    if text.strip():
        t = check_terminology(text, glossary)
        findings += t
        checks.append(_check("Terminology (glossary)", "rule", "ok", f"{len(glossary)} glossary entries checked, {len(t)} issues."))
        c, spans = check_claim_patterns(text, claims)
        findings += c
        f, stats = check_numeric_facts(text, facts)
        findings += f
        u = check_unverified_superlatives(text, spans)
        findings += u
        checks.append(_check("Claim verification (approved facts and claims)", "rule", "ok",
                             f"{stats['supported']} numeric claims supported, {len(f)} contradicted, "
                             f"{len(c)} matched claim rules, {len(u)} unverified."))
        s = check_style(text, guidelines, glossary)
        findings += s
        checks.append(_check("Style rules (exclamations, capitals, sentence length, readability)", "rule", "ok", f"{len(s)} issues."))
    else:
        checks.append(_check("Text checks", "rule", "skipped", "There is no text to check."))

    if image is not None:
        imf, imc = check_image(image, guidelines, colours)
        findings += imf
        checks += imc

    # optional AI step
    if not text.strip():
        pass
    elif confidential:
        checks.append(_check("AI tone and claim check", "ai", "skipped", "Confidential item: external AI is never used."))
    elif not allow_ai:
        checks.append(_check("AI tone and claim check", "ai", "skipped", "External AI is switched off by an admin."))
    elif ai_fn is None:
        checks.append(_check("AI tone and claim check", "ai", "skipped", "No AI key configured (set ANTHROPIC_API_KEY). Rule-based checks only."))
    else:
        try:
            raw = ai_fn(build_prompt(text, items))
            ai = validate_ai_findings(parse_ai_json(raw), text, items)
            rule_spans = [(f["start"], f["end"]) for f in findings if f["start"] >= 0]
            ai = [a for a in ai if not any(a["start"] < e and a["end"] > s for s, e in rule_spans)]
            findings += ai
            checks.append(_check("AI tone and claim check", "ai", "ok", f"{len(ai)} extra findings; every citation was verified in code."))
        except Exception as e:  # never block the whole report
            checks.append(_check("AI tone and claim check", "ai", "failed", f"AI check could not run: {e}"))

    seen, merged = set(), []
    for f in findings:
        key = (f["source_code"], f["start"], f["end"], f["quote"].lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(f)
    merged.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 3), f["start"] if f["start"] >= 0 else 10 ** 9))
    return merged, checks
