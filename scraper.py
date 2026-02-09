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

    # Abrir filtros avanzados
    page.evaluate(
        """
        () => {
            document.querySelector("#clickOtherFilters")?.click();
        }
        """
    )

    page.wait_for_timeout(3000)

    # Limpiar fechas de creación
    page.evaluate(
        """
        () => {
            document.querySelector("button.dev-clear-dates")?.click();
        }
        """
    )

    # Setear fechas de salida
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
            }
        }""",
        {
            "fromDate": DATE_FROM,
            "toDate": DATE_TO,
        },
    )

    # 🔑 SETEAR TIPO = HOTELS (SIN ESPERAR VISIBILIDAD)
    page.evaluate(
        """
        () => {
            const select = document.querySelector(
                "select[name='search-form:booking-filters:searchType']"
            );
            if (select) {
                select.value = "HOTELS";
                select.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
        """
    )

    # Estado = Reservado
    page.evaluate(
        """
        () => {
            document.querySelectorAll(".ui-chkbox-box").forEach(e => {
                if (e.textContent.includes("Reservado")) {
                    e.click();
                }
            });
        }
        """
    )

    # Aplicar filtros
    page.evaluate(
        """
        () => {
            document.querySelector("button.applyFilters")?.click();
        }
        """
    )

    page.wait_for_load_state("networkidle")


def export_excel(page, filepath):
    with page.expect_download() as download_info:
        page.evaluate(
            """
            () => {
                document.querySelector("button:has(.icon-download)")?.click();
            }
            """
        )
        page.click("text=Excel")

    download_info.value.save_as(filepath)


# ======================================================
# MAIN
# ======================================================

def run():
    print("Starting scraper...")
    print("Output directory:", OUTPUT_DIR)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login(page)
        apply_filters(page)

        export_excel(page, BOOKINGS_FILE)

        page.goto(SERVICES_URL, timeout=60000)
        page.wait_for_load_state("networkidle")
        export_excel(page, SERVICES_FILE)

        context.close()
        browser.close()

    print("DONE")
    print(f"- {BOOKINGS_FILE}")
    print(f"- {SERVICES_FILE}")


if __name__ == "__main__":
    run()
