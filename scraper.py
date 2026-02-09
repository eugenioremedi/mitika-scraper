import os
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

# Vista de reservas / servicios
BOOKINGS_URL = "https://mitika.travel/admin/bookings/List.xhtml?reset=true"

USERNAME = os.environ.get("MITIKA_USERNAME")
PASSWORD = os.environ.get("MITIKA_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("MITIKA_USERNAME and MITIKA_PASSWORD must be set")

TODAY = datetime.today()
DATE_FROM = (TODAY + timedelta(days=10)).strftime("%d/%m/%Y")
DATE_TO = (TODAY + timedelta(days=360)).strftime("%d/%m/%Y")
STAMP = TODAY.strftime("%Y_%m_%d")

SERVICES_FILE = os.path.join(OUTPUT_DIR, f"SERVICES_{STAMP}.xlsx")

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

    # Buscar = Services / Alojamiento (si aplica)
    page.evaluate(
        """
        () => {
            const select = document.querySelector(
                "select[name='search-form:booking-filters:searchType']"
            );
            if (select) {
                select.value = "SERVICES";
                select.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
        """
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


def export_services_excel(page, filepath):
    """
    Export correcto PrimeFaces:
    ejecuta EXACTAMENTE el onclick real del <a> Excel
    y captura la respuesta HTTP (no download)
    """
    with page.expect_response(
        lambda r: (
            "content-disposition" in r.headers
            and "attachment" in r.headers["content-disposition"].lower()
        ),
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
    content = response.body()

    with open(filepath, "wb") as f:
        f.write(content)


# ======================================================
# MAIN
# ======================================================

def run():
    print("Starting SERVICES export (PrimeFaces-safe)")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Dates: {DATE_FROM} → {DATE_TO}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        login(page)
        apply_filters(page)
        export_services_excel(page, SERVICES_FILE)

        context.close()
        browser.close()

    print("DONE")
    print(f"- {SERVICES_FILE}")


if __name__ == "__main__":
    run()
