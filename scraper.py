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


def set_date_input(page, input_id, value):
    """Set a PrimeFaces date input value reliably."""
    page.evaluate(
        """({ inputId, val }) => {
            const input = document.getElementById(inputId);
            if (!input) return;
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSetter.call(input, val);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        {"inputId": input_id, "val": value},
    )


def close_any_popups(page):
    """Close any open calendar popups or overlays."""
    page.evaluate("""() => {
        // Hide all PrimeFaces datepicker panels
        document.querySelectorAll(
            '.p-datepicker-panel, .ui-datepicker, .p-datepicker, ' +
            '.p-connected-overlay, .p-component-overlay'
        ).forEach(el => {
            el.style.display = 'none';
        });
        // Click the sidebar header area to dismiss popups
        const header = document.querySelector('.c-sticky-header');
        if (header) header.click();
    }""")


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
    page.evaluate("""() => {
        const all = document.querySelectorAll('button, a');
        for (const el of all) {
            if (el.textContent.trim() === 'Eliminar fechas') {
                el.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(1000)

    cleared = page.evaluate("""() => ({
        from: document.getElementById('search-form:booking-filters:creationDateFrom_input')?.value || '',
        to: document.getElementById('search-form:booking-filters:creationDateTo_input')?.value || ''
    })""")
    print(f"  Creation dates: from='{cleared['from']}', to='{cleared['to']}'")

    # ── Step 3: Expand "Fecha de salida" and set departure dates ──
    print("  Expanding 'Fecha de salida'...")
    page.locator("text=Fecha de salida").first.click()
    page.wait_for_timeout(1500)

    print(f"  Setting departure Desde: {DATE_FROM}")
    set_date_input(page, "search-form:booking-filters:departureDateFrom_input", DATE_FROM)
    page.wait_for_timeout(500)
    close_any_popups(page)
    page.wait_for_timeout(300)

    print(f"  Setting departure Hasta: {DATE_TO}")
    set_date_input(page, "search-form:booking-filters:departureDateTo_input", DATE_TO)
    page.wait_for_timeout(500)
    close_any_popups(page)
    page.wait_for_timeout(300)

    # Verify both dates
    dep_dates = page.evaluate("""() => ({
        from: document.getElementById('search-form:booking-filters:departureDateFrom_input')?.value || '',
        to: document.getElementById('search-form:booking-filters:departureDateTo_input')?.value || ''
    })""")
    print(f"  Departure dates: from='{dep_dates['from']}', to='{dep_dates['to']}'")
    screenshot(page, "04_dates_set")

    # ── Step 4: Close any remaining popups and scroll to bottom of sidebar ──
    print("  Closing popups and scrolling to Estado...")
    close_any_popups(page)
    page.wait_for_timeout(500)

    # Press Escape to dismiss any open calendar
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Scroll the filter sidebar to the very bottom
    page.evaluate("""() => {
        const containers = [
            document.querySelector('#search-form\\\\:booking-filters\\\\:search-form'),
            document.querySelector('.c-hidden-aside__scroller'),
            document.getElementById('c-hidden-aside--booking-filters'),
        ];
        for (const c of containers) {
            if (c) c.scrollTop = c.scrollHeight;
        }
    }""")
    page.wait_for_timeout(1000)

    screenshot(page, "05_scrolled_to_bottom")

    # ── Step 5: Expand "Estado" accordion ──
    print("  Expanding 'Estado' accordion...")

    # Use scrollIntoView on the dropdownStatus container to make sure we can see it
    page.evaluate("""() => {
        const dd = document.getElementById('dropdownStatus');
        if (dd) dd.scrollIntoView({ behavior: 'instant', block: 'center' });
    }""")
    page.wait_for_timeout(500)

    # Click the Estado header — it's a sibling/parent of dropdownStatus
    estado_result = page.evaluate("""() => {
        // Strategy 1: Find the "Estado" text element and click it
        const sidebar = document.getElementById('c-hidden-aside--booking-filters');
        if (!sidebar) return 'sidebar_not_found';

        // The accordion headers are typically div or span elements
        const walker = document.createTreeWalker(
            sidebar, NodeFilter.SHOW_TEXT, null, false
        );
        while (walker.nextNode()) {
            if (walker.currentNode.textContent.trim() === 'Estado') {
                const parent = walker.currentNode.parentElement;
                if (parent) {
                    parent.click();
                    return 'clicked_text_parent: ' + parent.tagName + ' ' + parent.className.substring(0, 40);
                }
            }
        }

        // Strategy 2: Find the dropdown container's preceding sibling/header
        const dd = document.getElementById('dropdownStatus');
        if (dd) {
            // The accordion header is usually the previous sibling or parent's first child
            let header = dd.previousElementSibling;
            if (header) {
                header.click();
                return 'clicked_prev_sibling: ' + header.tagName;
            }
            // Try parent
            const parent = dd.parentElement;
            if (parent) {
                const firstChild = parent.querySelector('div, span, h3, summary');
                if (firstChild && firstChild !== dd) {
                    firstChild.click();
                    return 'clicked_parent_first_child: ' + firstChild.tagName;
                }
            }
        }

        return 'not_found';
    }""")
    print(f"  Estado expand: {estado_result}")
    page.wait_for_timeout(1500)

    # Check if dropdownStatus is now visible
    dd_visible = page.evaluate("""() => {
        const dd = document.getElementById('dropdownStatus');
        if (!dd) return { exists: false };
        return {
            exists: true,
            display: window.getComputedStyle(dd).display,
            visibility: window.getComputedStyle(dd).visibility,
            height: dd.offsetHeight,
            childCount: dd.children.length
        };
    }""")
    print(f"  dropdownStatus state: {dd_visible}")

    # If still hidden, force it visible
    if dd_visible.get('display') == 'none' or dd_visible.get('height', 0) == 0:
        print("  ⚠️ Estado still hidden, forcing visible...")
        page.evaluate("""() => {
            const dd = document.getElementById('dropdownStatus');
            if (!dd) return;
            dd.style.display = 'block';
            dd.style.visibility = 'visible';
            dd.style.height = 'auto';
            dd.style.overflow = 'visible';
            dd.style.maxHeight = 'none';
            // Also make parent visible
            let parent = dd.parentElement;
            while (parent && parent.id !== 'c-hidden-aside--booking-filters') {
                parent.style.display = 'block';
                parent.style.visibility = 'visible';
                parent.style.height = 'auto';
                parent.style.overflow = 'visible';
                parent.style.maxHeight = 'none';
                parent = parent.parentElement;
            }
        }""")
        page.wait_for_timeout(500)

    screenshot(page, "06_estado_state")

    # ── Step 6: Uncheck all statuses, keep only "Reservado" ──
    print("  Setting status = Reservado only...")

    # First, list what we see
    checkbox_state = page.evaluate("""() => {
        const container = document.getElementById('dropdownStatus');
        if (!container) return { error: 'no container' };

        const items = [];
        const checkboxes = container.querySelectorAll('.ui-chkbox');
        for (const chk of checkboxes) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const parent = chk.closest('div');
            const label = parent?.querySelector('label');
            const text = label?.textContent.trim() || '';
            const isChecked = box?.classList.contains('ui-state-active') ||
                              icon?.classList.contains('ui-icon-check');
            items.push({ text, checked: isChecked });
        }
        return { count: checkboxes.length, items };
    }""")
    print(f"  Checkboxes found: {checkbox_state.get('count', 0)}")
    for item in checkbox_state.get('items', []):
        print(f"    [{('✓' if item['checked'] else ' ')}] {item['text']}")

    # Now toggle them
    status_result = page.evaluate("""() => {
        const container = document.getElementById('dropdownStatus');
        if (!container) return ['container not found'];

        const results = [];
        const checkboxes = container.querySelectorAll('.ui-chkbox');

        for (const chk of checkboxes) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const parent = chk.closest('div');
            const label = parent?.querySelector('label');
            const text = label?.textContent.trim() || '';
            const isChecked = box?.classList.contains('ui-state-active') ||
                              icon?.classList.contains('ui-icon-check');

            if (text === 'Reservado') {
                if (!isChecked && box) {
                    box.click();
                    results.push('checked: Reservado');
                } else {
                    results.push('already checked: Reservado');
                }
            } else if (text && isChecked && box) {
                box.click();
                results.push('unchecked: ' + text);
            }
        }

        return results;
    }""")
    print(f"  Status changes: {status_result}")

    # Verify final state
    final_state = page.evaluate("""() => {
        const container = document.getElementById('dropdownStatus');
        if (!container) return [];
        const items = [];
        for (const chk of container.querySelectorAll('.ui-chkbox')) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const parent = chk.closest('div');
            const label = parent?.querySelector('label');
            const text = label?.textContent.trim() || '';
            const isChecked = box?.classList.contains('ui-state-active') ||
                              icon?.classList.contains('ui-icon-check');
            items.push({ text, checked: isChecked });
        }
        return items;
    }""")
    print("  Final status state:")
    for item in final_state:
        print(f"    [{('✓' if item['checked'] else ' ')}] {item['text']}")

    screenshot(page, "07_status_set")

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
    screenshot(page, "08_after_apply")

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
