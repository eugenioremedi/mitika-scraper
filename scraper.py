import os
import traceback
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ======================================================
# PATHS
# ======================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ======================================================
# CONFIG
# ======================================================

LOGIN_URL = (
    "https://mitika.travel/login.xhtml?"
    "microsite=itravel&keepurl=true&url=%2Fhome%3FtripId%3D64"
)
BOOKINGS_URL = "https://mitika.travel/admin/bookings/List.xhtml"
SERVICES_URL = "https://mitika.travel/admin/bookings/List.xhtml?view=services"

USERNAME = os.environ.get("MITIKA_USERNAME")
PASSWORD = os.environ.get("MITIKA_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("MITIKA_USERNAME and MITIKA_PASSWORD must be set")

TODAY = datetime.today()
DATE_FROM = (TODAY + timedelta(days=10)).strftime("%d/%m/%Y")
DATE_TO = (TODAY + timedelta(days=360)).strftime("%d/%m/%Y")
STAMP = TODAY.strftime("%Y_%m_%d")

BOOKINGS_FILE = os.path.join(OUTPUT_DIR, f"BOOKINGS_{STAMP}.xlsx")
SERVICES_FILE = os.path.join(OUTPUT_DIR, f"SERVICES_{STAMP}.xlsx")


def screenshot(page, name):
    """Save a diagnostic screenshot to output dir."""
    path = os.path.join(OUTPUT_DIR, f"debug_{name}_{STAMP}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 Screenshot saved: {path}")


# ======================================================
# STEPS
# ======================================================

def login(page):
    print("[1/4] Logging in...")
    page.goto(LOGIN_URL, timeout=60000)
    page.wait_for_load_state("networkidle")

    page.fill("#login-form\\:login-content\\:login\\:Email", USERNAME)
    page.fill("#login-form\\:login-content\\:login\\:j_password", PASSWORD)
    page.click("button:has-text('Siguiente')")

    # Dismiss cookie banner if present
    try:
        accept_btn = page.locator("button:has-text('Aceptar todo')")
        if accept_btn.count():
            accept_btn.click(timeout=5000)
    except PwTimeout:
        pass

    page.wait_for_load_state("networkidle")
    screenshot(page, "01_after_login")

    # Verify login succeeded — check we're not still on login page
    if "login" in page.url.lower():
        screenshot(page, "01_login_FAILED")
        raise RuntimeError(f"Login appears to have failed. Still on: {page.url}")

    print(f"  ✅ Logged in. Current URL: {page.url}")


def apply_filters(page):
    print("[2/4] Applying filters...")
    page.goto(BOOKINGS_URL, timeout=60000)
    page.wait_for_load_state("networkidle")
    screenshot(page, "02_bookings_page")

    # Open advanced filters
    page.evaluate("""() => document.querySelector("#clickOtherFilters")?.click()""")
    page.wait_for_timeout(3000)
    screenshot(page, "03_filters_opened")

    # Clear creation dates
    page.evaluate("""() => document.querySelector("button.dev-clear-dates")?.click()""")

    # Set departure dates
    page.evaluate(
        """({ fromDate, toDate }) => {
            const f = document.getElementById(
                "search-form:booking-filters:departureDateFrom_input"
            );
            const t = document.getElementById(
                "search-form:booking-filters:departureDateTo_input"
            );
            if (f && t) {
                f.value = fromDate;
                t.value = toDate;
                f.dispatchEvent(new Event("change", { bubbles: true }));
                t.dispatchEvent(new Event("change", { bubbles: true }));
            } else {
                console.warn("SCRAPER: departure date inputs not found");
            }
        }""",
        {"fromDate": DATE_FROM, "toDate": DATE_TO},
    )

    # Set search type = HOTELS (direct DOM, no visibility wait)
    result = page.evaluate(
        """
        () => {
            const select = document.querySelector(
                "select[name='search-form:booking-filters:searchType']"
            );
            if (select) {
                select.value = "HOTELS";
                select.dispatchEvent(new Event("change", { bubbles: true }));
                return "set";
            }
            return "not_found";
        }
        """
    )
    print(f"  searchType select: {result}")

    # Check "Reservado" — look for label text, not checkbox box text
    result = page.evaluate(
        """
        () => {
            let clicked = 0;
            // Strategy 1: labels containing "Reservado"
            document.querySelectorAll("label").forEach(label => {
                if (label.textContent.trim().includes("Reservado")) {
                    label.click();
                    clicked++;
                }
            });
            // Strategy 2: PrimeFaces checkbox rows
            if (!clicked) {
                document.querySelectorAll(".ui-chkbox").forEach(chk => {
                    const parent = chk.closest("tr, li, div");
                    if (parent && parent.textContent.includes("Reservado")) {
                        const box = chk.querySelector(".ui-chkbox-box");
                        if (box) { box.click(); clicked++; }
                    }
                });
            }
            return clicked;
        }
        """
    )
    print(f"  Reservado checkboxes clicked: {result}")

    # Apply filters
    page.evaluate("""() => document.querySelector("button.applyFilters")?.click()""")
    page.wait_for_load_state("networkidle")
    screenshot(page, "04_filters_applied")

    # Log what we see
    count = page.evaluate(
        """() => document.querySelectorAll("table tbody tr").length"""
    )
    print(f"  ✅ Filters applied. Table rows visible: {count}")


def export_excel(page, exporter_id, filepath, label):
    """
    Try multiple strategies to trigger the PrimeFaces Excel export:
      1. expect_download with el.click()
      2. expect_download with PrimeFaces.ab()
      3. expect_response with Content-Disposition header
    """
    print(f"[Export] {label} → {filepath}")

    # First, check if the exporter element exists at all
    exists = page.evaluate(
        f'() => !!document.getElementById("{exporter_id}")'
    )
    print(f"  Exporter element exists: {exists}")

    if not exists:
        # Dump page HTML snippet for debugging
        snippet = page.evaluate(
            """() => {
                const els = document.querySelectorAll('[id*="export"], [id*="excel"]');
                return Array.from(els).map(e => e.id).join(', ') || 'none found';
            }"""
        )
        print(f"  ⚠️  Export-related elements on page: {snippet}")
        screenshot(page, f"export_missing_{label}")

    # ---------- Strategy 1: click() + expect_download ----------
    try:
        print("  Trying strategy 1: el.click() + expect_download ...")
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate(
                f"""() => {{
                    const el = document.getElementById("{exporter_id}");
                    if (el) el.click();
                }}"""
            )
        dl_info.value.save_as(filepath)
        print(f"  ✅ Strategy 1 worked!")
        return
    except PwTimeout:
        print("  ⏱️  Strategy 1 timed out.")

    # ---------- Strategy 2: PrimeFaces.ab() + expect_download ----------
    try:
        print("  Trying strategy 2: PrimeFaces.ab() + expect_download ...")
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate(
                f"""() => {{
                    if (typeof PrimeFaces !== 'undefined' && PrimeFaces.ab) {{
                        try {{
                            PrimeFaces.monitorDataExporterDownload(
                                () => {{}}, () => {{}}
                            );
                        }} catch(e) {{}}
                        PrimeFaces.ab({{
                            s: "{exporter_id}",
                            f: "search-form"
                        }});
                    }}
                }}"""
            )
        dl_info.value.save_as(filepath)
        print(f"  ✅ Strategy 2 worked!")
        return
    except PwTimeout:
        print("  ⏱️  Strategy 2 timed out.")

    # ---------- Strategy 3: PrimeFaces.ab() + expect_response ----------
    try:
        print("  Trying strategy 3: PrimeFaces.ab() + expect_response ...")
        with page.expect_response(
            lambda r: "content-disposition" in (
                {k.lower(): v for k, v in r.headers.items()}
            )
            and "attachment" in r.headers.get("content-disposition", r.headers.get("Content-Disposition", "")),
            timeout=60000,
        ) as resp_info:
            page.evaluate(
                f"""() => {{
                    if (typeof PrimeFaces !== 'undefined' && PrimeFaces.ab) {{
                        try {{
                            PrimeFaces.monitorDataExporterDownload(
                                () => {{}}, () => {{}}
                            );
                        }} catch(e) {{}}
                        PrimeFaces.ab({{
                            s: "{exporter_id}",
                            f: "search-form"
                        }});
                    }}
                }}"""
            )
        body = resp_info.value.body()
        with open(filepath, "wb") as f:
            f.write(body)
        print(f"  ✅ Strategy 3 worked! ({len(body)} bytes)")
        return
    except PwTimeout:
        print("  ⏱️  Strategy 3 timed out.")

    # ---------- All strategies failed ----------
    screenshot(page, f"export_FAILED_{label}")
    raise RuntimeError(
        f"All export strategies failed for {label}. "
        f"Check debug screenshots in {OUTPUT_DIR}"
    )


# ======================================================
# MAIN
# ======================================================

def run():
    print("=" * 60)
    print("Starting scraper...")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Date range: {DATE_FROM} → {DATE_TO}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            login(page)
            apply_filters(page)

            # BOOKINGS
            export_excel(
                page,
                "search-form:BOOKINGS:export-bookings:excel-exporter",
                BOOKINGS_FILE,
                "BOOKINGS",
            )

            # SERVICES
            page.goto(SERVICES_URL, timeout=60000)
            page.wait_for_load_state("networkidle")
            screenshot(page, "05_services_page")

            export_excel(
                page,
                "search-form:SERVICES:export-services:excel-exporter",
                SERVICES_FILE,
                "SERVICES",
            )

        except Exception:
            screenshot(page, "CRASH")
            traceback.print_exc()
            raise

        finally:
            context.close()
            browser.close()

    print("=" * 60)
    print("DONE ✅")
    print(f"  - {BOOKINGS_FILE}")
    print(f"  - {SERVICES_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    run()
