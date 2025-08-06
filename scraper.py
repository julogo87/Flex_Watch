import os
import sys
import time
import pandas as pd
from datetime import datetime
from g4f.client import Client
from playwright.sync_api import sync_playwright, Error

# This script is designed to be called from the command line.
# It expects one argument: the airport ICAO code.

def manejar_pagina_bienvenida(page):
    """Handles the welcome screen by clicking the accept button if it appears."""
    bienvenida_locator = "button:has-text(\"I've read and understood above statements\")"
    try:
        if page.locator(bienvenida_locator).is_visible(timeout=3000):
            page.click(bienvenida_locator)
            time.sleep(2)
    except Error:
        pass

def buscar_y_descargar_notams(aeropuerto):
    """Automates Firefox to search and download NOTAMs for a single airport."""
    print(f"INFO: Starting Playwright process for {aeropuerto}...")
    download_dir = os.path.join(os.getcwd(), "descargas_notam")
    os.makedirs(download_dir, exist_ok=True)
    
    try:
        with sync_playwright() as p:
            print(f"INFO: Launching headless browser...")
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
                accept_downloads=True
            )
            page = context.new_page()
            print(f"INFO: Navigating to FAA portal...")
            page.goto("https://notams.aim.faa.gov/notamSearch/", wait_until="domcontentloaded")
            manejar_pagina_bienvenida(page)
            
            input_locator = "input[name='designatorsForLocation']"
            page.wait_for_selector(input_locator, timeout=10000)
            page.fill(input_locator, aeropuerto)
            page.press(input_locator, "Enter")
            manejar_pagina_bienvenida(page)

            print(f"INFO: Waiting for data table...")
            page.wait_for_function(
                "() => document.querySelectorAll('table.table.table-striped').length > 0 && document.querySelectorAll('table.table.table-striped')[0].rows.length > 1",
                timeout=30000
            )
            
            print(f"INFO: Downloading NOTAM file...")
            download_locator = "span.icon-excel"
            with page.expect_download() as download_info:
                page.click(download_locator)
            
            download = download_info.value
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(download_dir, f"NOTAMs_{aeropuerto}_{timestamp}.xls")
            download.save_as(file_path)
            
            context.close()
            browser.close()
            print(f"INFO: Download successful. File saved at {file_path}")
            return file_path
            
    except Exception as e:
        print(f"ERROR: A Playwright error occurred: {e}")
        return None

def analizar_notams_con_ia(ruta_archivo, aeropuerto):
    """Reads the downloaded file and sends it to the IA for analysis."""
    print(f"INFO: Analyzing file {ruta_archivo} with AI...")
    try:
        df = pd.read_excel(ruta_archivo, skiprows=4)
        df.columns = ["Location", "NOTAM #/LTA #", "Class", "Issue Date (UTC)",
                      "Effective Date (UTC)", "Expiration Date (UTC)", "Condition"]
        
        if df.empty:
            return f"✅ No se encontraron NOTAMs activos para **{aeropuerto}**."
            
        datos_texto = df.to_string()
        prompt = f"""
        Eres un asistente experto en operaciones aéreas. Analiza los siguientes NOTAMs para el aeropuerto {aeropuerto}.
        Clasifícalos por tipo (CIERRES DE PISTA, OBSTÁCULOS, RODAJE, etc.), explica su impacto y genera un resumen final con los puntos más críticos.
        Presenta el resultado en Markdown.
        DATOS DE NOTAMs:
        {datos_texto}
        """
        client = Client()
        response = client.chat.completions.create(
            model="gpt-4-turbo", messages=[{"role": "user", "content": prompt}]
        )
        if not response.choices or not response.choices[0].message.content:
            raise Exception("La respuesta de la IA llegó vacía.")
        
        print("INFO: AI analysis complete.")
        return response.choices[0].message.content

    except Exception as e:
        error_msg = f"❌ Error durante el análisis con IA para {aeropuerto}: {e}"
        print(f"ERROR: {error_msg}")
        return error_msg

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("ERROR: Usage: python scraper.py <ICAO_CODE>")
        sys.exit(1)
        
    icao_code = sys.argv[1]
    
    # This is the file the Streamlit app will look for
    result_filename = f"notam_result_{icao_code}.txt"

    downloaded_file = buscar_y_descargar_notams(icao_code)
    
    if downloaded_file:
        summary = analizar_notams_con_ia(downloaded_file, icao_code)
        # Save the final summary to a text file
        with open(result_filename, "w", encoding="utf-8") as f:
            f.write(summary)
        os.remove(downloaded_file) # Clean up the excel file
        print(f"SUCCESS: Summary saved to {result_filename}")
        sys.exit(0) # Exit with success code
    else:
        # Create an error file if download fails
        with open(result_filename, "w", encoding="utf-8") as f:
            f.write(f"❌ No se pudo descargar la información de NOTAMs para {icao_code}.")
        print(f"ERROR: Failed to download NOTAMs for {icao_code}.")
        sys.exit(1) # Exit with error code