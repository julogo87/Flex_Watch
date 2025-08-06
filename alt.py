import sys
import asyncio
import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from g4f.client import Client

# Fix para asyncio en Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

def manejar_pagina_bienvenida(page, max_retries=5):
    """
    Da clic en el disclaimer de la FAA todas las veces que sea necesario.
    """
    bienvenida_locator = "button:has-text(\"I've read and understood above statements\")"
    for _ in range(max_retries):
        try:
            page.wait_for_selector(bienvenida_locator, timeout=5000)
            page.click(bienvenida_locator)
            time.sleep(2)
            # Si después de dar clic sigue el disclaimer, repite (máximo 5 veces)
            if not "notamSearch" in page.url:
                continue
            else:
                break
        except PlaywrightTimeoutError:
            # Si no aparece el botón, simplemente continúa
            break
        except Exception:
            break

def buscar_y_descargar_notams(aeropuertos):
    """
    Descarga el archivo de NOTAMs de la FAA para el aeropuerto dado.
    Devuelve la ruta al archivo descargado, o None si hubo error.
    """
    current_dir = os.getcwd()
    download_dir = os.path.join(current_dir, "descargas")
    os.makedirs(download_dir, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True
            )
            page = context.new_page()
            # 1. Entra a la página
            page.goto("https://notams.aim.faa.gov/notamSearch/", wait_until="domcontentloaded")
            manejar_pagina_bienvenida(page)
            # 2. Espera el input ICAO
            input_locator = "input[name='designatorsForLocation']"
            try:
                page.wait_for_selector(input_locator, timeout=12000)
            except PlaywrightTimeoutError:
                # Si no aparece el input, tal vez el disclaimer sigue, inténtalo otra vez
                manejar_pagina_bienvenida(page)
                page.wait_for_selector(input_locator, timeout=8000)
            page.fill(input_locator, ", ".join(aeropuertos))
            page.press(input_locator, "Enter")
            manejar_pagina_bienvenida(page)
            # 3. Espera a que cargue la tabla de NOTAMs
            st.info(f"Esperando la tabla de NOTAMs para {aeropuertos[0]}...")
            page.wait_for_function(
                "() => document.querySelectorAll('table.table.table-striped').length > 0 && document.querySelectorAll('table.table.table-striped')[0].rows.length > 1",
                timeout=30000
            )
            # 4. Ordena por Location
            page.click("th:has-text('Location')")
            time.sleep(1)
            # 5. Descarga Excel
            download_locator = "span.icon-excel"
            page.wait_for_selector(download_locator, timeout=10000)
            with page.expect_download() as download_info:
                page.click(download_locator)
            download = download_info.value
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            copy_path = os.path.join(download_dir, f"NOTAMs_{aeropuertos[0]}_{timestamp}.xls")
            download.save_as(copy_path)
            context.close()
            browser.close()
            return copy_path
    except Exception as e:
        st.error(f"Error durante la búsqueda para {aeropuertos[0]}: {e}")
        return None

def analizar_notams_con_ia(ruta_descarga, aeropuerto_actual):
    """
    Analiza el archivo Excel de NOTAMs con IA y devuelve un resumen.
    """
    try:
        df = pd.read_excel(ruta_descarga, skiprows=4)
        df.columns = ["Location", "NOTAM #/LTA #", "Class", "Issue Date (UTC)",
                      "Effective Date (UTC)", "Expiration Date (UTC)", "Condition"]
        if df.empty:
            return f"No se encontraron NOTAMs para {aeropuerto_actual}."
        datos_texto = df.to_string()
        prompt = f"""
        Eres un asistente experto en operaciones aéreas y despacho de vuelos.
        A continuación, te proporciono la lista COMPLETA de NOTAMs para el aeropuerto {aeropuerto_actual}.
        Tu tarea es analizar CADA NOTAM, clasificarlos por tipo y generar un resumen general.

        DATOS DE NOTAMs para {aeropuerto_actual}:
        {datos_texto}

        Por favor, genera un informe resumido en español que contenga lo siguiente:
        1. Resumen de impacto operacional.
        2. Detalla NOTAMs críticos (cierres de pista, umbrales desplazados, combustible, NAVAIDs).
        3. Filtro por fecha (últimos 2 días).
        """
        client = Client()
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        resumen_texto = response.choices[0].message.content
        return resumen_texto
    except Exception as e:
        return f"Error durante el análisis con IA para {aeropuerto_actual}: {e}"

st.title("Analizador de NOTAMs FAA (IA integrada)")

aeropuertos_str = st.text_input("Ingresa códigos ICAO separados por coma (ej: SKRG, KMIA)", "")

if st.button("Descargar y analizar"):
    if not aeropuertos_str.strip():
        st.warning("Debes ingresar al menos un aeropuerto.")
    else:
        aeropuertos = [a.strip().upper() for a in aeropuertos_str.split(",") if a.strip()]
        for aeropuerto in aeropuertos:
            st.write(f"## Procesando {aeropuerto} ...")
            archivo = buscar_y_descargar_notams([aeropuerto])
            if archivo:
                st.success(f"Archivo descargado para {aeropuerto}.")
                resumen = analizar_notams_con_ia(archivo, aeropuerto)
                st.write("### Resumen de IA:")
                st.write(resumen)
                try:
                    os.remove(archivo)
                except Exception:
                    pass
            else:
                st.error(f"No se pudo descargar los NOTAMs de {aeropuerto}.")

st.caption("Powered by FLEX Cargo · FAA NOTAMs · Streamlit · Playwright · IA")
