"""Browser walkthrough of every page and button. Needs the server running: python run.py
Run: python tests/e2e.py [shots_dir]"""
import sys, os
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("BASE", "http://localhost:8000")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else None
errors = []

def shot(page, name):
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)

def login(page, who):
    page.goto(BASE + "/#/login")
    page.fill("#li-email", f"{who}@nova.test"); page.fill("#li-pw", "demo1234")
    page.get_by_role("button", name="Login", exact=True).click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

def logout(page):
    page.get_by_role("button", name="Logout").click()
    expect(page.get_by_role("link", name="Get Started")).to_be_visible()

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1360, "height": 900})
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)

    # 1 landing + 2 login
    page.goto(BASE + "/")
    expect(page.get_by_text("before you publish")).to_be_visible(); shot(page, "01-landing")
    page.get_by_role("link", name="Get Started").click()
    expect(page.locator("#rg-ws")).to_be_visible()
    page.get_by_role("link", name="Back to home").click()
    page.get_by_role("link", name="Login").first.click()
    page.get_by_role("button", name="Login", exact=True).click()   # empty -> wrong details message
    expect(page.get_by_text("incorrect")).to_be_visible(); shot(page, "02-login")
    page.get_by_role("button", name="Use demo account").click()
    page.get_by_role("button", name="Login", exact=True).click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    # 3 dashboard (manager)
    page.get_by_role("button", name="Approved").first.click()
    expect(page.get_by_text("App update email").first).to_be_visible(); shot(page, "03-dashboard")

    # 4 knowledge
    page.get_by_role("link", name="Knowledge Base").click()
    expect(page.get_by_text("Voice").first).to_be_visible()
    page.get_by_role("tab", name="Approved claims").click()
    expect(page.get_by_text("fastest").first).to_be_visible()
    page.get_by_role("tab", name="Guidelines").click(); shot(page, "04-knowledge")
    page.get_by_role("button", name="+ Add item").click()
    page.fill("#kf-title", "Be kind"); page.fill("#kf-body", "Always be kind to readers in every message.")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("cell", name="Be kind", exact=True)).to_be_visible()
    page.get_by_role("button", name="Publish version").click()
    expect(page.get_by_text("Published version: 2")).to_be_visible()
    # import a guideline file
    page.set_input_files("#kn-file", {"name": "rules.txt", "mimeType": "text/plain", "buffer": b"1. Always answer questions within two working days.\n2. Never promise delivery dates we cannot keep."})
    expect(page.get_by_text("Preview: 2 rules found")).to_be_visible()
    page.get_by_role("button", name="Save all rules").click()
    expect(page.get_by_text("Always answer questions").first).to_be_visible()
    page.get_by_role("button", name="Archive").last.click(); page.get_by_role("button", name="Archive").last.click()
    logout(page)

    # 5 new review + 6 report (creator)
    login(page, "creator")
    page.get_by_role("link", name="+ New Review").click()
    page.fill("#nr-title", "Launch post")
    page.fill("#nr-text", "Our app is the fastest in India and now supports 12 languages!!!")
    shot(page, "05-new-review")
    page.get_by_role("button", name="Run check").click()
    expect(page.get_by_text("What was checked")).to_be_visible()
    expect(page.locator(".fcard").first).to_be_visible(); shot(page, "06-report")
    page.get_by_role("button", name="What was checked").click()
    expect(page.get_by_text("No AI model was used")).to_be_visible(); shot(page, "06b-checks")
    page.get_by_role("button", name="Close").click()
    # submit is blocked while High findings are open
    page.get_by_role("button", name="Submit for approval").click()
    expect(page.get_by_text("High finding(s) are still open").first).to_be_visible()
    # accept fix on 'fastest'
    card = page.locator(".fcard", has_text="forbidden claim").first
    card.get_by_role("button", name="Accept fix").click()
    expect(page.locator("select[aria-label=Version]")).to_have_value("2")
    # edit fix on the contradicted number
    card = page.locator(".fcard", has_text="Approved fact F1").first
    card.get_by_role("button", name="Edit fix").click()
    page.locator(".modal input").fill("9"); page.get_by_role("button", name="Apply").click()
    expect(page.locator("select[aria-label=Version]")).to_have_value("3")
    # dismiss remaining Low findings with a reason
    page.get_by_role("button", name="Dismiss").first.click()
    page.locator(".modal select").select_option("Rule is unclear")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("button", name="Compare versions").click()
    expect(page.locator(".modal del").first).to_be_visible(); shot(page, "06c-compare")
    page.get_by_role("button", name="Close").click()
    page.get_by_role("button", name="Submit for approval").click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
    logout(page)

    # 7 approvals (reviewer) and approve
    login(page, "reviewer")
    page.get_by_role("link", name="Approvals", exact=True).click()
    expect(page.get_by_role("heading", name="Approvals")).to_be_visible()
    expect(page.get_by_text("Launch post")).to_be_visible(); shot(page, "07-approvals")
    page.get_by_role("button", name="Open next").click()
    expect(page.get_by_role("button", name="Approve")).to_be_visible()
    page.get_by_role("button", name="Approve").click()
    page.locator(".modal").get_by_role("button", name="Approve").click()
    expect(page.get_by_text("Approved and locked").first).to_be_visible(); shot(page, "06d-approved")
    expect(page.get_by_role("link", name="Export approval record")).to_be_visible()
    page.locator("textarea[aria-label='General comment']").fill("Nice work")
    page.get_by_role("button", name="Post").last.click()
    expect(page.get_by_text("Nice work").first).to_be_visible()
    logout(page)

    # 8 insights + 9 settings (admin)
    login(page, "admin")
    page.get_by_role("link", name="Insights").click()
    expect(page.get_by_text("Top repeated issues")).to_be_visible(); shot(page, "08-insights")
    page.get_by_role("link", name="Improve this rule").first.click()
    expect(page.get_by_role("heading", name="Edit")).to_be_visible()
    page.get_by_role("button", name="Cancel").click()
    page.get_by_role("link", name="Settings").click()
    expect(page.get_by_text("Invite user")).to_be_visible(); shot(page, "09-settings-team")
    page.get_by_role("tab", name="AI and data").click()
    expect(page.get_by_text("Anthropic Claude API")).to_be_visible(); shot(page, "09b-settings-ai")
    page.get_by_role("tab", name="Audit log").click()
    expect(page.get_by_text("review approve").or_(page.get_by_text("review_approve")).first).to_be_visible(); shot(page, "09c-audit")
    logout(page)
    # role limits: creator has no Insights link
    login(page, "creator")
    expect(page.get_by_role("link", name="Insights")).to_have_count(0)
    page.goto(BASE + "/#/insights"); expect(page.get_by_text("No access")).to_be_visible()

    # mobile width check: no horizontal scroll
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(BASE + "/#/dashboard"); page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2"), "horizontal scroll on mobile"
    shot(page, "10-mobile")
    b.close()

if errors:
    print("BROWSER ERRORS:"); [print(" ", e) for e in errors]; sys.exit(1)
print("E2E OK")
