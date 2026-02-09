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
    path = os.path.join(OUTPUT_DIR, f"debug_{name}_{STAMP}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 {name}")


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
        raise RuntimeError(f"Login failed. Still on: {page.url}")

    print(f"  ✅ Logged in. URL: {page.url}")


def apply_filters(page):
    print("[2/3] Applying filters...")
    page.goto(BOOKINGS_URL, timeout=60000)
    page.wait_for_load_state("networkidle")
    screenshot(page, "02_bookings_loaded")

    # ── Step 1: Open the Filtros sidebar ──
    print("  Opening filters sidebar...")
    page.locator("a.dev-open-filters").click()
    page.wait_for_timeout(2000)
    screenshot(page, "03_filters_opened")

    # ── Step 2: Clear creation dates ──
    print("  Clearing creation dates...")
    # The "Eliminar fechas" button inside the creation date section
    page.evaluate("""() => {
        const buttons = document.querySelectorAll('button.dev-clear-dates, a.dev-clear-dates');
        if (buttons.length > 0) {
            buttons[0].click();
            return;
        }
        // Fallback: find by text
        const all = document.querySelectorAll('button, a');
        for (const el of all) {
            if (el.textContent.trim() === 'Eliminar fechas') {
                el.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # Verify cleared
    cleared = page.evaluate("""() => ({
        from: document.getElementById('search-form:booking-filters:creationDateFrom_input')?.value || '',
        to: document.getElementById('search-form:booking-filters:creationDateTo_input')?.value || ''
    })""")
    print(f"  Creation dates: from='{cleared['from']}', to='{cleared['to']}'")

    # ── Step 3: Expand "Fecha de salida" and set departure dates ──
    print("  Expanding 'Fecha de salida'...")
    # Click the accordion header text
    page.locator("text=Fecha de salida").first.click()
    page.wait_for_timeout(1500)

    # Now the departure date inputs should be visible — set values via JS
    print(f"  Setting departure dates: {DATE_FROM} → {DATE_TO}")
    page.evaluate(
        """({ fromDate, toDate }) => {
            const fInput = document.getElementById('search-form:booking-filters:departureDateFrom_input');
            const tInput = document.getElementById('search-form:booking-filters:departureDateTo_input');

            function setDateValue(input, val) {
                if (!input) return;
                // Set the value via native setter to trigger PrimeFaces
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(input, val);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                // Also try focusing and blurring to trigger PrimeFaces datepicker
                input.dispatchEvent(new Event('focus', { bubbles: true }));
                input.dispatchEvent(new Event('blur', { bubbles: true }));
            }

            setDateValue(fInput, fromDate);
            setDateValue(tInput, toDate);
        }""",
        {"fromDate": DATE_FROM, "toDate": DATE_TO},
    )
    page.wait_for_timeout(1000)

    # Verify
    dep_dates = page.evaluate("""() => ({
        from: document.getElementById('search-form:booking-filters:departureDateFrom_input')?.value || '',
        to: document.getElementById('search-form:booking-filters:departureDateTo_input')?.value || ''
    })""")
    print(f"  Departure dates set: from='{dep_dates['from']}', to='{dep_dates['to']}'")
    screenshot(page, "04_dates_set")

    # ── Step 4: Scroll down in the filter sidebar to reach Estado ──
    # Scroll the filter sidebar container
    page.evaluate("""() => {
        const scroller = document.querySelector('.c-hidden-aside__scroller') ||
                         document.querySelector('#c-hidden-aside--booking-filters');
        if (scroller) scroller.scrollTop = scroller.scrollHeight;
    }""")
    page.wait_for_timeout(1000)

    # ── Step 5: Expand "Estado" accordion ──
    print("  Expanding 'Estado' section...")
    # The Estado section is inside the filter sidebar, might need to click to expand
    page.evaluate("""() => {
        // Find "Estado" text and click its parent accordion
        const elements = document.querySelectorAll(
            '#c-hidden-aside--booking-filters *'
        );
        for (const el of elements) {
            if (el.children.length === 0 && el.textContent.trim() === 'Estado') {
                // Click the closest clickable parent (the accordion header)
                const clickTarget = el.closest('[role="button"], summary, details, h2, h3, div') || el;
                clickTarget.click();
                return 'clicked';
            }
        }
        return 'not_found';
    }""")
    page.wait_for_timeout(1000)

    # Also try direct locator click
    try:
        page.locator("#c-hidden-aside--booking-filters >> text=Estado").first.click()
        page.wait_for_timeout(1000)
    except Exception:
        pass

    screenshot(page, "05_estado_expanded")

    # ── Step 6: Uncheck all statuses, keep only "Reservado" ──
    # From the video: there are 8 status checkboxes, all checked by default
    # statuses:0 = Reservado, :1 = Error de reserva, :2 = Pendiente,
    # :3 = No reservado, :4 = Parcialmente reservado, :5 = Cancelado,
    # :6 = Error en precio, :7 = Pendiente actualizar
    print("  Setting status = Reservado only...")
    status_result = page.evaluate("""() => {
        const results = [];
        const container = document.getElementById('dropdownStatus');
        if (!container) return { error: 'dropdownStatus not found' };

        // Get all PrimeFaces checkbox items within the status container
        const checkboxes = container.querySelectorAll('.ui-chkbox');

        for (const chk of checkboxes) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const label = chk.closest('div, li, tr')?.querySelector('label');
            const text = label?.textContent.trim() || '';
            const isChecked = box?.classList.contains('ui-state-active') ||
                              icon?.classList.contains('ui-icon-check');

            if (text === 'Reservado') {
                // Keep this one checked
                if (!isChecked) {
                    box?.click();
                    results.push('checked: ' + text);
                } else {
                    results.push('already checked: ' + text);
                }
            } else if (text) {
                // Uncheck everything else
                if (isChecked) {
                    box?.click();
                    results.push('unchecked: ' + text);
                }
            }
        }

        // Fallback: try using the input elements directly
        if (results.length === 0) {
            const inputs = container.querySelectorAll('input[type="checkbox"]');
            for (const input of inputs) {
                const parent = input.closest('div');
                const label = parent?.querySelector('label');
                const text = label?.textContent.trim() || '';

                if (text === 'Reservado') {
                    if (!input.checked) {
                        input.click();
                        results.push('input-checked: ' + text);
                    } else {
                        results.push('input-already-checked: ' + text);
                    }
                } else if (text && input.checked) {
                    input.click();
                    results.push('input-unchecked: ' + text);
                }
            }
        }

        return results;
    }""")
    print(f"  Status changes: {status_result}")
    screenshot(page, "06_status_set")

    # ── Step 7: Click "Aplicar" ──
    print("  Clicking Aplicar...")
    page.evaluate("""() => {
        const buttons = document.querySelectorAll('button, a');
        for (const btn of buttons) {
            if (btn.textContent.trim() === 'Aplicar') {
                btn.click();
                return;
            }
        }
    }""")

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)
    screenshot(page, "07_after_apply")

    # Check results
    result = page.evaluate("""() => {
        const rows = document.querySelectorAll('table tbody tr');
        const pager = document.querySelector('.ui-paginator-current');
        return {
            rowCount: rows.length,
            pagerText: pager ? pager.textContent.trim() : 'no pager'
        };
    }""")
    print(f"  ✅ After apply. Rows: {result['rowCount']}, Pager: {result['pagerText']}")


def export_excel(page, exporter_id, filepath, label):
    print(f"[3/3] Export {label} → {filepath}")

    exists = page.evaluate(f'() => !!document.getElementById("{exporter_id}")')
    print(f"  Exporter exists: {exists}")

    if not exists:
        # List all export-related elements
        snippet = page.evaluate("""() => {
            const els = document.querySelectorAll('[id*="export"], [id*="excel"], [id*="Export"]');
            return Array.from(els).map(e => e.id + ' (' + e.tagName + ')').join('\\n') || 'none';
        }""")
        print(f"  Export elements on page:\\n{snippet}")
        screenshot(page, "export_missing")

    # Strategy 1: click + expect_download
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

    # Strategy 2: PrimeFaces.ab + expect_download
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
        print("  Strategy 3: expect_response ...")
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
    raise RuntimeError(f"All export strategies failed for {label}")


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
