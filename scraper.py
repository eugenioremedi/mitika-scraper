"""
Mitika Travel — Export Bookings + Services (Alojamiento)
========================================================
Exports two Excel files from mitika.travel/admin/bookings:
  1. BOOKINGS_YYYY_MM_DD.xlsx  (booking-level, default view)
  2. SERVICES_YYYY_MM_DD.xlsx  (service-level, ?view=services / Alojamiento)

Filters applied:
  - Buscar: Alojamiento (HOTELS)
  - Estado: Reservado (RESERVED)
  - Fecha de salida: today+10 → today+360
  - Creation date filter removed

Environment variables:
  MITIKA_USERNAME
  MITIKA_PASSWORD

Usage:
  python scraper.py
"""

import os
import time
import traceback
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ======================================================
# PATHS  (kept compatible with GitHub Actions workflow)
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
STAMP = TODAY.strftime("%Y_%m_%d_%H%M")

BOOKINGS_FILE = os.path.join(OUTPUT_DIR, f"BOOKINGS_{STAMP}.xlsx")
SERVICES_FILE = os.path.join(OUTPUT_DIR, f"SERVICES_{STAMP}.xlsx")
PARAMS_FILE = os.path.join(OUTPUT_DIR, f"FILTER_PARAMS_{STAMP}.txt")

# Timeouts (ms)
NAV_TIMEOUT = 60_000
AJAX_TIMEOUT = 30_000
CLICK_TIMEOUT = 15_000


# ======================================================
# HELPERS
# ======================================================

def screenshot(page, name):
    path = os.path.join(OUTPUT_DIR, f"debug_{name}_{STAMP}.png")
    try:
        page.screenshot(path=path, full_page=True)
        print(f"  📸 {name}")
    except Exception as e:
        print(f"  ⚠ Screenshot failed: {e}")


def safe_goto(page, url, timeout=NAV_TIMEOUT):
    """Navigate to a URL, handling ERR_ABORTED from JSF redirects gracefully."""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    except Exception as e:
        if "ERR_ABORTED" in str(e):
            print(f"  ⚠ Navigation interrupted (ERR_ABORTED) — waiting for page to settle…")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except PwTimeout:
                pass
        else:
            raise
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PwTimeout:
        pass


def wait_for_ajax(page, timeout=AJAX_TIMEOUT):
    """Wait until PrimeFaces Ajax queue is idle."""
    try:
        page.wait_for_function(
            """() => {
                if (typeof PrimeFaces === 'undefined') return true;
                if (typeof PrimeFaces.ajax === 'undefined') return true;
                const queue = PrimeFaces.ajax.Queue;
                return !queue || queue.isEmpty();
            }""",
            timeout=timeout,
        )
    except PwTimeout:
        print("  ⚠ PrimeFaces Ajax wait timed out — continuing anyway")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PwTimeout:
        pass


def js_click(page, selector):
    """Click via JavaScript — bypasses viewport/visibility checks."""
    clicked = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) { el.click(); return true; }
            return false;
        }""",
        selector,
    )
    if not clicked:
        print(f"  ⚠ js_click: element not found for '{selector}'")
    return clicked


def save_filter_params():
    """Write a companion .txt with the filters used."""
    lines = [
        f"MITIKA — RESERVAS EXPORT LOG",
        f"{'=' * 44}",
        f"",
        f"Execution time : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"User           : {USERNAME}",
        f"URL (bookings) : {BOOKINGS_URL}",
        f"URL (services) : {SERVICES_URL}",
        f"",
        f"APPLIED FILTERS",
        f"{'-' * 24}",
        f"Buscar               : Alojamiento (HOTELS)",
        f"Estado               : Reservado (RESERVED)",
        f"Fecha de salida desde: {DATE_FROM}",
        f"Fecha de salida hasta: {DATE_TO}",
        f"Creation date filter : removed",
        f"",
        f"FILTER LOGIC",
        f"{'-' * 24}",
        f"From = today + 10 days  ({TODAY.date()} + 10 = {(TODAY + timedelta(days=10)).date()})",
        f"To   = today + 360 days ({TODAY.date()} + 360 = {(TODAY + timedelta(days=360)).date()})",
        f"PrimeFaces Ajax filters applied programmatically",
        f"Exported via Exportar → Excel",
        f"",
        f"OUTPUT FILES",
        f"{'-' * 24}",
        f"Bookings : BOOKINGS_{STAMP}.xlsx",
        f"Services : SERVICES_{STAMP}.xlsx",
    ]
    with open(PARAMS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  📝 Filter params saved: {PARAMS_FILE}")


# ======================================================
# STEPS
# ======================================================

def login(page):
    print("[1/4] Logging in...")
    safe_goto(page, LOGIN_URL)

    page.fill("#login-form\\:login-content\\:login\\:Email", USERNAME)
    page.fill("#login-form\\:login-content\\:login\\:j_password", PASSWORD)
    page.click("button:has-text('Siguiente')", timeout=CLICK_TIMEOUT)

    try:
        page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    except PwTimeout:
        pass
    time.sleep(3)

    # Dismiss cookie/consent banner if present
    try:
        accept_btn = page.locator("button:has-text('Aceptar todo')")
        if accept_btn.count() > 0:
            accept_btn.first.click(timeout=5_000)
            time.sleep(1)
    except PwTimeout:
        pass

    screenshot(page, "01_after_login")

    if "login" in page.url.lower():
        raise RuntimeError(f"Login failed. Still on: {page.url}")

    print(f"  ✅ Logged in. URL: {page.url}")


def navigate_to_admin_bookings(page):
    """Robustly navigate to the admin bookings page with retries."""
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        if "/admin/bookings" in page.url:
            print(f"  ✔ Already on admin bookings page")
            return

        print(f"  → Navigating to admin bookings (attempt {attempt}/{max_attempts})…")

        try:
            page.goto(BOOKINGS_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            if "ERR_ABORTED" in str(e):
                print(f"  ⚠ ERR_ABORTED — page may have redirected")
            else:
                print(f"  ⚠ Navigation error: {e}")

        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PwTimeout:
            pass
        time.sleep(2)

        if "/admin/bookings" in page.url:
            print(f"  ✔ Reached admin bookings page")
            return

        # Last resort: JS redirect
        try:
            page.evaluate(f"window.location.href = '{BOOKINGS_URL}'")
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            time.sleep(2)
            if "/admin/bookings" in page.url:
                print(f"  ✔ Reached admin bookings via JS redirect")
                return
        except Exception:
            pass

    screenshot(page, "admin_nav_failed")
    raise RuntimeError(
        f"Could not reach admin bookings page after {max_attempts} attempts. "
        f"Current URL: {page.url}"
    )


def apply_filters(page):
    """Navigate to bookings page and apply all filters."""
    print("[2/4] Applying filters...")
    navigate_to_admin_bookings(page)
    screenshot(page, "02_bookings_loaded")

    # ── Open filter panel ──
    print("  Opening filters sidebar...")
    opened = js_click(page, "#clickOtherFilters")
    if not opened:
        # Fallback: try the CSS class used in original scraper
        try:
            page.locator("a.dev-open-filters").click(timeout=CLICK_TIMEOUT)
        except PwTimeout:
            # Fallback: try text-based
            try:
                page.locator("a", has_text="Filtros").click(timeout=CLICK_TIMEOUT)
            except PwTimeout:
                print("  ⚠ Could not open filter panel")
                screenshot(page, "filter_panel_fail")

    # Wait for filter form
    try:
        page.wait_for_selector("#search-form", state="visible", timeout=AJAX_TIMEOUT)
    except PwTimeout:
        print("  ⚠ Filter form did not appear")
        screenshot(page, "filter_form_missing")

    time.sleep(1)
    screenshot(page, "03_filters_opened")

    # ── Remove default creation-date filter ──
    print("  Clearing creation dates...")
    js_click(page, "button.dev-clear-dates")
    if not js_click(page, "button.dev-clear-dates"):
        # Fallback: click "Eliminar fechas" by text
        page.evaluate("""() => {
            const all = document.querySelectorAll('button, a');
            for (const el of all) {
                if (el.textContent.trim() === 'Eliminar fechas') {
                    el.click();
                    return;
                }
            }
        }""")
    time.sleep(0.5)

    # ── Set departure dates via PrimeFaces Ajax ──
    print(f"  Setting departure dates: {DATE_FROM} → {DATE_TO}")
    page.evaluate(
        """([fromDate, toDate]) => {
            const fromInput = document.querySelector(
                "#search-form\\\\:booking-filters\\\\:departureDateFrom_input"
            );
            const toInput = document.querySelector(
                "#search-form\\\\:booking-filters\\\\:departureDateTo_input"
            );

            if (fromInput) fromInput.value = fromDate;
            if (toInput)   toInput.value = toDate;

            // Use PrimeFaces Ajax to notify the server
            if (typeof PrimeFaces !== 'undefined') {
                PrimeFaces.ab({
                    s: 'search-form:booking-filters:departureDateFrom',
                    e: 'change',
                    f: 'search-form',
                    p: 'search-form:booking-filters:departureDateFrom',
                    u: 'search-form'
                });
                PrimeFaces.ab({
                    s: 'search-form:booking-filters:departureDateTo',
                    e: 'change',
                    f: 'search-form',
                    p: 'search-form:booking-filters:departureDateTo',
                    u: 'search-form'
                });
            } else {
                fromInput?.dispatchEvent(new Event("change", { bubbles: true }));
                toInput?.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }""",
        [DATE_FROM, DATE_TO],
    )
    wait_for_ajax(page)
    print(f"  ✔ Departure dates set")

    # ── Buscar = Alojamiento (HOTELS) ──
    print("  Setting 'Buscar' to 'Alojamiento'...")
    try:
        page.get_by_label("Buscar:").select_option("HOTELS")
    except Exception:
        try:
            page.select_option(
                "select[name='search-form:booking-filters:searchType']", "HOTELS"
            )
        except Exception:
            # Last fallback: JS
            page.evaluate("""() => {
                const selects = document.querySelectorAll('select');
                for (const sel of selects) {
                    for (const opt of sel.options) {
                        if (opt.value === 'HOTELS' || opt.text.includes('Alojamiento')) {
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', { bubbles: true }));
                            return;
                        }
                    }
                }
            }""")
    print("  ✔ Buscar: Alojamiento")

    # ── Estado = Reservado only ──
    print("  Setting status = Reservado only...")
    page.evaluate(
        """() => {
            document.querySelectorAll(".ui-chkbox").forEach(cb => {
                const input = cb.querySelector("input[type='checkbox']");
                if (!input) return;
                const shouldBeChecked = (input.value === "RESERVED");
                if (input.checked !== shouldBeChecked) {
                    const box = cb.querySelector(".ui-chkbox-box");
                    if (box) box.click();
                }
            });
        }"""
    )
    time.sleep(0.5)
    print("  ✔ Estado: Reservado")

    screenshot(page, "04_filters_set")

    # ── Submit filters ──
    print("  Applying filters...")
    page.evaluate(
        """() => {
            if (typeof PrimeFaces !== 'undefined') {
                PrimeFaces.ab({
                    s: 'search-form:booking-filters:search',
                    f: 'search-form',
                    u: 'search-form'
                });
            }
        }"""
    )
    wait_for_ajax(page)

    # Also try clicking the apply button as fallback
    try:
        apply_btn = page.locator("button.applyFilters")
        if apply_btn.count() > 0:
            js_click(page, "button.applyFilters")
            wait_for_ajax(page)
    except Exception:
        pass

    # Extra fallback: click "Aplicar" by text
    page.evaluate("""() => {
        const buttons = document.querySelectorAll('button, a');
        for (const btn of buttons) {
            if (btn.textContent.trim() === 'Aplicar') {
                btn.click();
                return;
            }
        }
    }""")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PwTimeout:
        pass
    time.sleep(3)

    screenshot(page, "05_after_apply")

    result = page.evaluate("""() => {
        const rows = document.querySelectorAll('table tbody tr');
        const pager = document.querySelector('.ui-paginator-current');
        return {
            rowCount: rows.length,
            pagerText: pager ? pager.textContent.trim() : 'no pager'
        };
    }""")
    print(f"  ✅ After apply. Rows: {result['rowCount']}, Pager: {result['pagerText']}")


def export_excel(page, filepath, label):
    """Click Exportar → Excel and save the downloaded file."""
    print(f"  Exporting {label} → {filepath}")

    # Open the Exportar dropdown
    exportar_btn = page.locator("button:has-text('Exportar'), a:has-text('Exportar')")
    try:
        exportar_btn.first.click(timeout=CLICK_TIMEOUT)
    except PwTimeout:
        js_click(page, "[id$='exportButton']")

    time.sleep(0.5)

    # Click "Excel" in the dropdown and catch the download
    with page.expect_download(timeout=NAV_TIMEOUT) as download_info:
        excel_link = page.locator("a:has-text('Excel'), li:has-text('Excel') a")
        try:
            excel_link.first.click(timeout=CLICK_TIMEOUT)
        except PwTimeout:
            page.get_by_role("link", name="Excel").click(timeout=CLICK_TIMEOUT)

    download = download_info.value
    download.save_as(filepath)
    print(f"  ✅ Saved: {filepath}")


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
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.set_default_timeout(AJAX_TIMEOUT)

        try:
            login(page)
            apply_filters(page)

            # ── Export 1: Bookings (default view) ──
            print("[3/4] Exporting Bookings...")
            export_excel(page, BOOKINGS_FILE, "BOOKINGS")

            # ── Export 2: Services / Alojamiento ──
            print("[4/4] Switching to services view and exporting...")
            safe_goto(page, SERVICES_URL)
            wait_for_ajax(page)
            screenshot(page, "06_services_view")
            export_excel(page, SERVICES_FILE, "SERVICES")

            # ── Filter log ──
            save_filter_params()

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
    print(f"  - {PARAMS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    run()
