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

USERNAME = os.environ.get("MITIKA_USERNAME")
PASSWORD = os.environ.get("MITIKA_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("MITIKA_USERNAME and MITIKA_PASSWORD must be set")

TODAY = datetime.today()
DATE_FROM = (TODAY + timedelta(days=10)).strftime("%d/%m/%Y")
DATE_TO = (TODAY + timedelta(days=360)).strftime("%d/%m/%Y")
STAMP = TODAY.strftime("%Y_%m_%d")

BOOKINGS_FILE = os.path.join(OUTPUT_DIR, f"BOOKINGS_{STAMP}.xlsx")


def screenshot(page, name):
    """Save a diagnostic screenshot to output dir."""
    path = os.path.join(OUTPUT_DIR, f"debug_{name}_{STAMP}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 Screenshot: {path}")


# ======================================================
# STEPS
# ======================================================

def login(page):
    print("[1/3] Logging in...")
    page.goto(LOGIN_URL, timeout=60000)
    page.wait_for_load_state("networkidle")

    page.fill("#login-form\\:login-content\\:login\\:Email", USERNAME)
    page.fill("#login-form\\:login-content\\:login\\:j_password", PASSWORD)
    page.click("button:has-text('Siguiente')")

    try:
        accept_btn = page.locator("button:has-text('Aceptar todo')")
        if accept_btn.count():
            accept_btn.click(timeout=5000)
    except PwTimeout:
        pass

    page.wait_for_load_state("networkidle")
    screenshot(page, "01_after_login")

    if "login" in page.url.lower():
        screenshot(page, "01_login_FAILED")
        raise RuntimeError(f"Login failed. Still on: {page.url}")

    print(f"  ✅ Logged in. URL: {page.url}")


def apply_filters(page):
    print("[2/3] Applying filters...")
    page.goto(BOOKINGS_URL, timeout=60000)
    page.wait_for_load_state("networkidle")
    screenshot(page, "02_bookings_loaded")

    # ── DIAGNOSTIC: Dump all buttons and filter-related elements ──
    diag = page.evaluate("""() => {
        const info = {};

        info.buttons = Array.from(document.querySelectorAll('button')).map(b => ({
            id: b.id || '',
            text: b.textContent.trim().substring(0, 60),
            classes: b.className,
            visible: b.offsetParent !== null
        }));

        info.filtrosButton = Array.from(document.querySelectorAll('button, a, div, span'))
            .filter(e => e.textContent.trim().includes('Filtro'))
            .map(e => ({
                tag: e.tagName,
                id: e.id || '',
                text: e.textContent.trim().substring(0, 60),
                classes: e.className
            }));

        info.clickOtherFilters = !!document.querySelector('#clickOtherFilters');
        info.devClearDates = !!document.querySelector('button.dev-clear-dates');
        info.applyFilters = !!document.querySelector('button.applyFilters');

        info.filterElements = Array.from(document.querySelectorAll('[id*="filter" i], [class*="filter" i]'))
            .map(e => ({
                tag: e.tagName,
                id: e.id || '',
                classes: e.className.substring(0, 80)
            })).slice(0, 20);

        return info;
    }""")

    print(f"  #clickOtherFilters exists: {diag['clickOtherFilters']}")
    print(f"  button.dev-clear-dates exists: {diag['devClearDates']}")
    print(f"  button.applyFilters exists: {diag['applyFilters']}")
    print(f"  Filtros-related elements: {len(diag['filtrosButton'])}")
    for el in diag['filtrosButton']:
        print(f"    <{el['tag']} id='{el['id']}' class='{el['classes']}'> {el['text']}")
    print(f"  Filter-related elements: {len(diag['filterElements'])}")
    for el in diag['filterElements'][:10]:
        print(f"    <{el['tag']} id='{el['id']}' class='{el['classes'][:60]}>")

    # ── Try clicking the Filtros button (visible in screenshots) ──
    try:
        filtros_btn = page.locator("button:has-text('Filtros'), a:has-text('Filtros')").first
        if filtros_btn.count():
            print("  Clicking 'Filtros' button...")
            filtros_btn.click()
            page.wait_for_timeout(3000)
            screenshot(page, "03_after_filtros_click")
        else:
            print("  ⚠️  No 'Filtros' button found via locator")
    except Exception as e:
        print(f"  ⚠️  Error clicking Filtros: {e}")

    # Also try the old selector
    page.evaluate("""() => document.querySelector("#clickOtherFilters")?.click()""")
    page.wait_for_timeout(2000)

    # ── DIAGNOSTIC: What's in the filters panel now? ──
    filter_panel = page.evaluate("""() => {
        const info = {};

        info.selects = Array.from(document.querySelectorAll('select')).map(s => ({
            name: s.name || '',
            id: s.id || '',
            options: Array.from(s.options).map(o => o.value + '=' + o.text).slice(0, 10),
            visible: s.offsetParent !== null
        }));

        info.dateInputs = Array.from(document.querySelectorAll('input[id*="date" i], input[id*="Date" i], input[id*="fecha" i]'))
            .map(i => ({
                id: i.id || '',
                name: i.name || '',
                value: i.value || '',
                visible: i.offsetParent !== null
            }));

        info.checkboxes = Array.from(document.querySelectorAll('.ui-chkbox, input[type="checkbox"]'))
            .map(c => {
                const parent = c.closest('tr, li, div, label');
                return {
                    id: c.id || '',
                    text: parent ? parent.textContent.trim().substring(0, 60) : '',
                    classes: c.className
                };
            }).slice(0, 20);

        info.statusElements = Array.from(document.querySelectorAll('[id*="status" i], [id*="estado" i], [id*="state" i]'))
            .map(e => ({
                tag: e.tagName,
                id: e.id || '',
                text: e.textContent.trim().substring(0, 80)
            })).slice(0, 10);

        return info;
    }""")

    print(f"\n  📋 SELECT elements: {len(filter_panel['selects'])}")
    for s in filter_panel['selects']:
        print(f"    <select name='{s['name']}' id='{s['id']}' visible={s['visible']}>")
        for o in s['options'][:5]:
            print(f"      {o}")

    print(f"\n  📋 Date inputs: {len(filter_panel['dateInputs'])}")
    for d in filter_panel['dateInputs']:
        print(f"    <input id='{d['id']}' value='{d['value']}' visible={d['visible']}>")

    print(f"\n  📋 Checkboxes: {len(filter_panel['checkboxes'])}")
    for c in filter_panel['checkboxes'][:10]:
        print(f"    id='{c['id']}' text='{c['text'][:50]}'")

    print(f"\n  📋 Status-related elements: {len(filter_panel['statusElements'])}")
    for s in filter_panel['statusElements']:
        print(f"    <{s['tag']} id='{s['id']}'> {s['text'][:60]}")

    screenshot(page, "04_filter_panel_state")

    # ── Set departure dates ──
    date_result = page.evaluate(
        """({ fromDate, toDate }) => {
            const ids = [
                "search-form:booking-filters:departureDateFrom_input",
                "search-form:booking-filters:departureDateTo_input"
            ];
            const found = ids.map(id => !!document.getElementById(id));
            const f = document.getElementById(ids[0]);
            const t = document.getElementById(ids[1]);
            if (f && t) {
                f.value = fromDate;
                t.value = toDate;
                f.dispatchEvent(new Event("change", { bubbles: true }));
                t.dispatchEvent(new Event("change", { bubbles: true }));
            }
            return { fromFound: found[0], toFound: found[1] };
        }""",
        {"fromDate": DATE_FROM, "toDate": DATE_TO},
    )
    print(f"\n  Date inputs found: from={date_result['fromFound']}, to={date_result['toFound']}")

    # ── Set searchType = HOTELS ──
    search_result = page.evaluate("""() => {
        const select = document.querySelector("select[name='search-form:booking-filters:searchType']");
        if (select) {
            select.value = "HOTELS";
            select.dispatchEvent(new Event("change", { bubbles: true }));
            return "set_to_HOTELS";
        }
        return "not_found";
    }""")
    print(f"  searchType: {search_result}")

    # ── Check "Reservado" ──
    reservado_result = page.evaluate("""() => {
        let clicked = 0;
        let found = [];

        // Strategy 1: labels
        document.querySelectorAll("label").forEach(label => {
            if (label.textContent.trim().includes("Reservado")) {
                found.push("label: " + label.textContent.trim().substring(0, 40));
                label.click();
                clicked++;
            }
        });

        // Strategy 2: PrimeFaces checkbox parents
        if (!clicked) {
            document.querySelectorAll(".ui-chkbox").forEach(chk => {
                const parent = chk.closest("tr, li, div");
                if (parent && parent.textContent.includes("Reservado")) {
                    found.push("chkbox-parent: " + parent.textContent.trim().substring(0, 40));
                    const box = chk.querySelector(".ui-chkbox-box");
                    if (box) { box.click(); clicked++; }
                }
            });
        }

        // Strategy 3: just report any "Reservado" text on page
        if (!clicked) {
            document.querySelectorAll("span, div, td, li").forEach(el => {
                if (el.textContent.trim() === "Reservado" || el.textContent.trim() === "Reservado") {
                    found.push(el.tagName + ": " + el.id + " / " + el.className);
                }
            });
        }

        return { clicked, found };
    }""")
    print(f"  Reservado: clicked={reservado_result['clicked']}, found={reservado_result['found']}")

    # ── Apply filters ──
    apply_result = page.evaluate("""() => {
        const selectors = [
            "button.applyFilters",
            "[id*='applyFilter']",
            "[id*='searchButton']",
            "[id*='search-button']",
            "[id*='btnSearch']",
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) { el.click(); return "clicked: " + sel; }
        }

        const btns = Array.from(document.querySelectorAll("button, a"));
        for (const btn of btns) {
            const t = btn.textContent.trim().toLowerCase();
            if (t.includes("buscar") || t.includes("aplicar") || t.includes("search") || t.includes("apply")) {
                btn.click();
                return "clicked by text: " + btn.textContent.trim().substring(0, 30);
            }
        }

        return "no_apply_button_found";
    }""")
    print(f"  Apply filters: {apply_result}")

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    screenshot(page, "05_after_apply_filters")

    count = page.evaluate("""() => document.querySelectorAll("table tbody tr").length""")
    print(f"  ✅ After filters. Table rows: {count}")


def export_excel(page, exporter_id, filepath, label):
    print(f"[3/3] Export {label} → {filepath}")

    exists = page.evaluate(f'() => !!document.getElementById("{exporter_id}")')
    print(f"  Exporter element exists: {exists}")

    if not exists:
        snippet = page.evaluate("""() => {
            const els = document.querySelectorAll('[id*="export"], [id*="excel"], [id*="Export"]');
            return Array.from(els).map(e => e.id).join('\\n') || 'none found';
        }""")
        print(f"  ⚠️  Export-related elements:\\n{snippet}")
        screenshot(page, f"export_missing_{label}")

    # Strategy 1: click() + expect_download
    try:
        print("  Strategy 1: el.click() + expect_download ...")
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate(f"""() => {{
                const el = document.getElementById("{exporter_id}");
                if (el) el.click();
            }}""")
        dl_info.value.save_as(filepath)
        print(f"  ✅ Strategy 1 worked!")
        return
    except PwTimeout:
        print("  ⏱️  Strategy 1 timed out.")

    # Strategy 2: PrimeFaces.ab() + expect_download
    try:
        print("  Strategy 2: PrimeFaces.ab() + expect_download ...")
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate(f"""() => {{
                if (typeof PrimeFaces !== 'undefined' && PrimeFaces.ab) {{
                    try {{ PrimeFaces.monitorDataExporterDownload(() => {{}}, () => {{}}); }} catch(e) {{}}
                    PrimeFaces.ab({{ s: "{exporter_id}", f: "search-form" }});
                }}
            }}""")
        dl_info.value.save_as(filepath)
        print(f"  ✅ Strategy 2 worked!")
        return
    except PwTimeout:
        print("  ⏱️  Strategy 2 timed out.")

    # Strategy 3: expect_response
    try:
        print("  Strategy 3: PrimeFaces.ab() + expect_response ...")
        with page.expect_response(
            lambda r: "attachment" in r.headers.get("content-disposition", ""),
            timeout=60000,
        ) as resp_info:
            page.evaluate(f"""() => {{
                if (typeof PrimeFaces !== 'undefined' && PrimeFaces.ab) {{
                    try {{ PrimeFaces.monitorDataExporterDownload(() => {{}}, () => {{}}); }} catch(e) {{}}
                    PrimeFaces.ab({{ s: "{exporter_id}", f: "search-form" }});
                }}
            }}""")
        body = resp_info.value.body()
        with open(filepath, "wb") as f:
            f.write(body)
        print(f"  ✅ Strategy 3 worked! ({len(body)} bytes)")
        return
    except PwTimeout:
        print("  ⏱️  Strategy 3 timed out.")

    screenshot(page, f"export_FAILED_{label}")
    raise RuntimeError(f"All export strategies failed for {label}. Check screenshots in {OUTPUT_DIR}")


# ======================================================
# MAIN
# ======================================================

def run():
    print("=" * 60)
    print("Starting scraper...")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Dates: {DATE_FROM} → {DATE_TO}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            login(page)
            apply_filters(page)
            export_excel(
                page,
                "search-form:BOOKINGS:export-bookings:excel-exporter",
                BOOKINGS_FILE,
                "BOOKINGS",
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
    print("=" * 60)


if __name__ == "__main__":
    run()
