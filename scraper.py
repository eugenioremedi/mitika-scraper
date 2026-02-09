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
# BASE64 DETECTION (ROBUST)
# ======================================================
BASE64_PATTERN = re.compile(
    r"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,([A-Za-z0-9+/=\s]+)",
    re.DOTALL,
)

def extract_excel_from_text(text: str, output_path: str) -> bool:
    """
    Busca un data:application/...;base64 en cualquier texto,
    lo decodifica y guarda el XLSX.
    Devuelve True si lo encontró.
    """
    match = BASE64_PATTERN.search(text)
    if not match:
        return False
    
    b64 = match.group(1)
    b64 = re.sub(r"\s+", "", b64)  # limpia saltos de línea
    
    data = base64.b64decode(b64)
    
    with open(output_path, "wb") as f:
        f.write(data)
    
    return True

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
    page.evaluate("() => document.querySelector('#clickOtherFilters')?.click()")
    page.wait_for_timeout(2000)
    
    # Limpiar fechas de creación
    page.evaluate("() => document.querySelector('button.dev-clear-dates')?.click()")
    
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
    page.evaluate("() => document.querySelector('button.applyFilters')?.click()")
    page.wait_for_load_state("networkidle")

def export_excel_from_base64(page):
    """
    Dispara el export PrimeFaces y escanea TODAS las responses
    hasta encontrar el Excel embebido en base64.
    """
    found = {"ok": False}
    
    def on_response(response):
        if found["ok"]:
            return
        try:
            text = response.text()
        except Exception:
            return
        if extract_excel_from_text(text, EXCEL_FILE):
            found["ok"] = True
    
    # Add listener
    page.on("response", on_response)
    
    # Disparar EXACTAMENTE el onclick real
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
    
    # Esperar hasta que aparezca el Excel (máx 2 min)
    page.wait_for_timeout(120000)
    
    # Remove listener - CORRECTED: use remove_listener instead of off
    page.remove_listener("response", on_response)
    
    if not found["ok"]:
        raise RuntimeError("No se pudo capturar el Excel desde ninguna response")

# ======================================================
# MAIN
# ======================================================
def run():
    print("Starting Mitika Excel export (PrimeFaces base64 robust)")
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