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
PARAMS_FILE = os.path.join(OUTPUT_DIR, f"FILTER_PARAMS_{STAMP}.txt")


def screenshot(page, name):
    path = os.path.join(OUTPUT_DIR, f"debug_{name}_{STAMP}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 {name}")


def save_filter_params(actual_dates, actual_statuses):
    """Save the filter parameters used to a text file."""
    lines = [
        f"Fecha de ejecución: {TODAY.strftime('%d/%m/%Y %H:%M')}",
        f"",
        f"=== PARÁMETROS DE FILTRO ===",
        f"",
        f"Fecha de creación: Sin filtro (eliminadas)",
        f"",
        f"Fecha de salida:",
        f"  Desde: {DATE_FROM}",
        f"  Hasta: {DATE_TO}",
        f"",
        f"Buscar: Bookings",
        f"",
        f"Estado: Solo Reservado",
        f"  (Desmarcados: Error de reserva, Pendiente, No reservado,",
        f"   Parcialmente reservado, Cancelado, Error en precio,",
        f"   Pendiente actualizar)",
        f"",
        f"=== VALORES REALES APLICADOS ===",
        f"",
        f"Fecha de creación (Desde): {actual_dates.get('creation_from', 'N/A')}",
        f"Fecha de creación (Hasta): {actual_dates.get('creation_to', 'N/A')}",
        f"Fecha de salida (Desde):   {actual_dates.get('departure_from', 'N/A')}",
        f"Fecha de salida (Hasta):   {actual_dates.get('departure_to', 'N/A')}",
        f"",
        f"Estados marcados: {', '.join(actual_statuses) if actual_statuses else 'N/A'}",
        f"",
        f"Archivo exportado: BOOKINGS_{STAMP}.xlsx",
    ]
    with open(PARAMS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  📝 Filter params saved: {PARAMS_FILE}")


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

    # ── Step 2: Click "Eliminar fechas" on creation dates ──
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

    # ── Step 3: Expand "Fecha de salida" accordion ──
    print("  Expanding 'Fecha de salida'...")
    page.locator("text=Fecha de salida").first.click()
    page.wait_for_timeout(1500)

    # ── Step 4: Set departure dates ──
    print(f"  Setting departure dates: {DATE_FROM} → {DATE_TO}")

    # Use triple-click + type to clear & fill the inputs reliably
    dep_from_id = "search-form:booking-filters:departureDateFrom_input"
    dep_to_id = "search-form:booking-filters:departureDateTo_input"

    # Set Desde
    dep_from = page.locator(f"#{dep_from_id.replace(':', '\\\\:')}")
    dep_from.click()
    page.wait_for_timeout(300)
    dep_from.fill("")
    dep_from.type(DATE_FROM, delay=50)
    page.keyboard.press("Escape")  # Close calendar popup
    page.wait_for_timeout(500)

    # Set Hasta
    dep_to = page.locator(f"#{dep_to_id.replace(':', '\\\\:')}")
    dep_to.click()
    page.wait_for_timeout(300)
    dep_to.fill("")
    dep_to.type(DATE_TO, delay=50)
    page.keyboard.press("Escape")  # Close calendar popup
    page.wait_for_timeout(500)

    # Verify
    dep_dates = page.evaluate("""() => ({
        from: document.getElementById('search-form:booking-filters:departureDateFrom_input')?.value || '',
        to: document.getElementById('search-form:booking-filters:departureDateTo_input')?.value || ''
    })""")
    print(f"  Departure dates: from='{dep_dates['from']}', to='{dep_dates['to']}'")
    screenshot(page, "04_dates_set")

    # ── Step 5: Scroll sidebar to bottom and expand Estado ──
    print("  Scrolling to Estado section...")

    # Scroll the filter sidebar to the very bottom
    page.evaluate("""() => {
        const sidebar = document.getElementById('c-hidden-aside--booking-filters');
        if (sidebar) sidebar.scrollTop = sidebar.scrollHeight;
    }""")
    page.wait_for_timeout(1000)

    # Now click "Estado" to expand it
    print("  Expanding 'Estado' accordion...")
    page.evaluate("""() => {
        const sidebar = document.getElementById('c-hidden-aside--booking-filters');
        if (!sidebar) return;
        const walker = document.createTreeWalker(sidebar, NodeFilter.SHOW_TEXT, null, false);
        while (walker.nextNode()) {
            if (walker.currentNode.textContent.trim() === 'Estado') {
                const parent = walker.currentNode.parentElement;
                if (parent) parent.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    # Scroll again to make sure checkboxes are visible
    page.evaluate("""() => {
        const sidebar = document.getElementById('c-hidden-aside--booking-filters');
        if (sidebar) sidebar.scrollTop = sidebar.scrollHeight;
    }""")
    page.wait_for_timeout(500)

    screenshot(page, "05_estado_expanded")

    # ── Step 6: Check current checkbox state ──
    checkbox_state = page.evaluate("""() => {
        const container = document.getElementById('dropdownStatus');
        if (!container) return { error: 'no container', html: '' };

        const items = [];
        const checkboxes = container.querySelectorAll('.ui-chkbox');
        for (const chk of checkboxes) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const parent = chk.closest('div, li, tr');
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

    # ── Step 7: Uncheck all except Reservado ──
    print("  Setting status = Reservado only...")
    status_result = page.evaluate("""() => {
        const container = document.getElementById('dropdownStatus');
        if (!container) return ['container not found'];

        const results = [];
        const checkboxes = container.querySelectorAll('.ui-chkbox');

        for (const chk of checkboxes) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const parent = chk.closest('div, li, tr');
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
    page.wait_for_timeout(500)

    # Verify final checkbox state
    final_state = page.evaluate("""() => {
        const container = document.getElementById('dropdownStatus');
        if (!container) return [];
        const items = [];
        for (const chk of container.querySelectorAll('.ui-chkbox')) {
            const box = chk.querySelector('.ui-chkbox-box');
            const icon = chk.querySelector('.ui-chkbox-icon');
            const parent = chk.closest('div, li, tr');
            const label = parent?.querySelector('label');
            const text = label?.textContent.trim() || '';
            const isChecked = box?.classList.contains('ui-state-active') ||
                              icon?.classList.contains('ui-icon-check');
            items.push({ text, checked: isChecked });
        }
        return items;
    }""")
    checked_statuses = [item['text'] for item in final_state if item.get('checked')]
    print("  Final status state:")
    for item in final_state:
        print(f"    [{('✓' if item['checked'] else ' ')}] {item['text']}")

    screenshot(page, "06_status_set")

    # ── Step 8: Verify departure dates weren't cleared by scrolling ──
    pre_apply_dates = page.evaluate("""() => ({
        creation_from: document.getElementById('search-form:booking-filters:creationDateFrom_input')?.value || '',
        creation_to: document.getElementById('search-form:booking-filters:creationDateTo_input')?.value || '',
        departure_from: document.getElementById('search-form:booking-filters:departureDateFrom_input')?.value || '',
        departure_to: document.getElementById('search-form:booking-filters:departureDateTo_input')?.value || ''
    })""")
    print(f"  Pre-apply dates: {pre_apply_dates}")

    # If departure dates were lost, re-set them
    if not pre_apply_dates['departure_from'] or not pre_apply_dates['departure_to']:
        print("  ⚠️ Departure dates were cleared! Re-setting...")
        page.evaluate(
            """({ fromDate, toDate }) => {
                function setVal(id, val) {
                    const input = document.getElementById(id);
                    if (!input) return;
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeSetter.call(input, val);
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
                setVal('search-form:booking-filters:departureDateFrom_input', fromDate);
                setVal('search-form:booking-filters:departureDateTo_input', toDate);
            }""",
            {"fromDate": DATE_FROM, "toDate": DATE_TO},
        )
        page.wait_for_timeout(500)

        # Verify again
        pre_apply_dates = page.evaluate("""() => ({
            creation_from: document.getElementById('search-form:booking-filters:creationDateFrom_input')?.value || '',
            creation_to: document.getElementById('search-form:booking-filters:creationDateTo_input')?.value || '',
            departure_from: document.getElementById('search-form:booking-filters:departureDateFrom_input')?.value || '',
            departure_to: document.getElementById('search-form:booking-filters:departureDateTo_input')?.value || ''
        })""")
        print(f"  After re-set: {pre_apply_dates}")

    screenshot(page, "07_pre_apply")

    # ── Step 9: Click "Aplicar" ──
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

    # Save filter params
    save_filter_params(pre_apply_dates, checked_statuses)


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
    print(f"  - {PARAMS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    run()
