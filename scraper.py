import os
import re
import base64
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

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

BOOKINGS_URL = "https://mitika.travel/admin/bookings/List.xhtml?reset=true"

USERNAME = os.environ.get("MITIKA_USERNAME")
PASSWORD = os.environ.get("MITIKA_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("MITIKA_USERNAME and MITIKA_PASSWORD must be set")

TODAY = datetime.today()
DATE_FROM = (TODAY + timedelta(days=10)).strftime("%d/%m/%Y")
DATE_TO = (TODAY + timedelta(days=360)).strftime("%d/%m/%Y")
STAMP = TODAY.strftime("%Y_%m_%d")

EXCEL_FILE = os.path.join(OUTPUT_DIR, f"BOOKINGS_{STAMP}.xlsx")

# ======================================================
# HELPERS
# ======================================================

BASE64_REGEX = re.compile(
    r"data:application/vnd\.openxmlformats-officedocument\.spreadsheetml\.sheet;base64,([A-Za-z0-9+/=]+)"
)

def extract_excel_from_response(text: str, output_path: str):
    """
    Busca el data:application/...;base64 dentro de la response,
    lo decodifica y guarda el XLSX
    """
    match = BASE64_REGEX.search(text)
    if not match:
        raise RuntimeError("No se encontró contenido base64 del Excel en la response")

    excel_b64 = match.group(1)
    excel_bytes = base64.b64decode(excel_b64)

    with open(output_path, "wb") as f:
        f.write(excel_bytes)

# ======================================================
# STEPS
# ======================================================

def login(page):
    page.goto(LOGIN_URL, timeout=60000)

    page.fill("#login-form\\:login-content\\:login\\:Email", USERNAME)
    page.fill("#login-form\\:login-content\\:login\\:j_password", PASSWORD)
    page.click("button:has-text('Siguiente')")

    if page.locator("button:has-text('Aceptar todo')").count():
        page.click("button:has-text('Aceptar todo')")

    page.wait_for_load_state("networkidle")


def apply_filters(page):
    page.goto(BOOKINGS_URL, timeout=60000)
    page.wait_for_load_state("networkidle")

    # Abrir filtros
    page.evaluate(
        "() => document.querySelector('#clickOtherFilters')?.click()"
    )
    page.wait_for_timeout(2000)

    # Limpiar fechas de creación
    page.evaluate(
        "() => document.querySelector('button.dev-clear-dates')?.click()"
    )

    # Fechas de salida
    page.evaluate(
        """({ fromDate, toDate }) => {
            const f = document.getElementById(
                'search-form:booking-filters:departureDateFrom_input'
            );
            const t = document.getElementById(
                'search-form:booking-filters:departureDateTo_input'
            );
            if (f && t) {
                f.value = fromDate;
                t.value = toDate;
                f.dispatchEvent(new Event('change', { bubbles: true }));
                t.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        {"fromDate": DATE_FROM, "toDate": DATE_TO},
    )

    # Estado = solo Reservado
    page.evaluate(
        """
        () => {
            document.querySelectorAll('.ui-chkbox-box').forEach(e => {
                const active = e.classList.contains('ui-state-active');
                const isReservado = e.textContent.includes('Reservado');
                if (active && !isReservado) e.click();
                if (!active && isReservado) e.click();
            });
        }
        """
    )

    # Aplicar filtros
    page.evaluate(
        "() => document.querySelector('button.applyFilters')?.click()"
    )
    page.wait_for_load_state("networkidle")


def export_excel_from_base64(page):
    """
    Dispara el export PrimeFaces y captura la response AJAX
    para extraer el Excel embebido en base64
    """

    with page.expect_response(
        lambda r: r.url.endswith("/admin/bookings/List.xhtml") and r.request.method == "POST",
        timeout=120000,
    ) as response_info:
        page.evaluate(
            """
            () => {
                PrimeFaces.monitorDataExporterDownload(
                    travelc.admin.blockPage,
                    travelc.admin.unblockPage
                );
                PrimeFaces.ab({
                    s: 'search-form:services:export-services:excel-exporter',
                    f: 'search-form'
                });
            }
            """
        )

    response = response_info.value
    body = response.text()

    extract_excel_from_response(body, EXCEL_FILE)

# ======================================================
# MAIN
# ======================================================

def run():
    print("Starting Mitika Excel export (base64 mode)")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Dates: {DATE_FROM} → {DATE_TO}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        login(page)
        apply_filters(page)
        export_excel_from_base64(page)

        context.close()
        browser.close()

    print("DONE")
    print(f"- {EXCEL_FILE}")

if __name__ == "__main__":
    run()
