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

# 🔑 RESET DE ESTADO DE GRILLA (CLAVE PARA COLUMNAS COMPLETAS)
BOOKINGS_URL = (
    "https://mitika.travel/admin/bookings/List.xhtml?reset=true"
)

USERNAME = os.environ.get("MITIKA_USERNAME")
PASSWORD = os.environ.get("MITIKA_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("MITIKA_USERNAME and MITIKA_PASSWORD must be set")

TODAY = datetime.today()
DATE_FROM = (TODAY + timedelta(days=10)).strftime("%d/%m/%Y")
DATE_TO = (TODAY + timedelta(days=360)).strftime("%d/%m/%Y")
STAMP = TODAY.strftime("%Y_%m_%d")

BOOKINGS_FILE = os.path.join(OUTPUT_DIR, f"BOOKINGS_{STAMP}.xlsx")

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

    # Fechas de salida (Desde / Hasta)
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


def export_bookings(page):
    # Exportar > Excel (BOOKINGS)
    page.locator("button:has-text('Exportar')").click()
    page.wait_for_timeout(1000)

    with page.expect_download(timeout=60000) as download_info:
        page.locator("text=Excel").click()

    download = download_info.value
    download.save_as(BOOKINGS_FILE)


# ======================================================
# MAIN
# ======================================================

def run():
    print("Starting BOOKINGS scraper")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Departure dates: {DATE_FROM} → {DATE_TO}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login(page)
        apply_filters(page)
        export_bookings(page)

        context.close()
        browser.close()

    print("DONE")
    print(f"- {BOOKINGS_FILE}")


if __name__ == "__main__":
    run()
