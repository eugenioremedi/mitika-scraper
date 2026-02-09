import os
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# =========================
# CONFIG
# =========================

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

BOOKINGS_FILE = f"BOOKINGS_{STAMP}.xlsx"
SERVICES_FILE = f"SERVICES_{STAMP}.xlsx"


# =========================
# STEPS
# =========================

def login(page):
    page.goto(LOGIN_URL, timeout=60000)

    page.fill("#login-form\\:login-content\\:login\\:Email", USERNAME)
    page.fill("#login-form\\:login-content\\:login\\:j_password", PASSWORD)
    page.click("button:has-text('Siguiente')")

    # Accept terms if shown
    if page.locator("button:has-text('Aceptar todo')").count():
        page.click("button:has-text('Aceptar todo')")

    page.wait_for_load_state("networkidle")


def apply_filters(page):
    page.goto(BOOKINGS_URL, timeout=60000)
    page.wait_for_load_state("networkidle")

    # Open filters panel (JS click – REQUIRED)
    page.evaluate("""
    () => {
        const btn = document.querySelector("#clickOtherFilters");
        if (btn) btn.click();
    }
    """)

    page.wait_for_selector("#search-form", timeout=30000)

    # Clear creation dates (JS click – REQUIRED)
    page.evaluate("""
    () => {
        const btn = document.querySelector("button.dev-clear-dates");
        if (btn) btn.click();
    }
    """)

    # Set Fecha de salida (PrimeFaces-safe)
    page.evaluate(
        """(fromDate, toDate) => {
            const f = document.getElementById(
                "search-form:booking-filters:departureDateFrom_input"
            );
            const t = document.getElementById(
                "search-form:booking-filters:departureDateTo_input"
            );

            f.value = fromDate;
            t.value = toDate;

            f.dispatchEvent(new Event("change", { bubbles: true }));
            t.dispatchEvent(new Event("change", { bubbles: true }));
        }""",
        DATE_FROM,
        DATE_TO
    )

    # Buscar = Alojamiento
    page.select_option(
        "select[name='search-form:booking-filters:searchType']",
        "HOTELS"
    )

    # Estado = Reservado (JS – no viewport dependency)
    page.evaluate("""
    () => {
        document.querySelectorAll(".ui-chkbox-box").forEach(e => {
            if (e.textContent.includes("Reservado")) {
                e.click();
            }
        });
    }
    """)

    # Apply filters
    page.evaluate("""
    () => {
        const btn = document.querySelector("button.applyFilters");
        if (btn) btn.click();
    }
    """)

    page.wait_for_load_state("networkidle")


def export_excel(page, filename):
    with page.expect_download() as d:
        page.evaluate("""
        () => {
            document
              .querySelector("button:has(.icon-download), button:has-text('Exportar')")
              ?.click();
        }
        """)
        page.click("text=Excel")
    d.value.save_as(filename)


# =========================
# MAIN
# =========================

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login(page)
        apply_filters(page)

        # Export BOOKINGS (summary)
        export_excel(page, BOOKINGS_FILE)

        # Export SERVICES (detail)
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
