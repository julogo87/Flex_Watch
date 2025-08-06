import streamlit as st
import pandas as pd
import os
import sys
import time
import asyncio
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from g4f.client import Client

# --- Cargar la base de datos de pistas al iniciar ---
@st.cache_resource
def load_runway_data():
    """Carga el archivo runways.csv en un DataFrame de Pandas."""
    try:
        runway_path = os.path.join("assets", "runways.csv")
        return pd.read_csv(runway_path)
    except FileNotFoundError:
        st.error("Error: No se encontró `runways.csv` en la carpeta `assets`.")
        st.error("Por favor, descárgalo desde https://ourairports.com/data/ y colócalo en la carpeta `assets`.")
        return None

runways_df = load_runway_data()

# --- Lógica de Respaldo de IA ---
AI_MODELS = ["gpt-4o-mini", "gemini-2.5-flash", "grok-3", "gpt-4.1-mini"]

def call_ai_with_fallback(prompt, model_list):
    for model in model_list:
        try:
            if model != model_list[0]:
                st.warning(f"El modelo principal falló. Reintentando con `{model}`...")
            client = Client()
            response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            raise Exception("Respuesta de IA vacía.")
        except Exception as e:
            print(f"Modelo {model} falló con error: {e}")
            continue
    return "❌ Todos los modelos de IA fallaron. Por favor, inténtalo de nuevo más tarde."

# Fix para asyncio en Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configuración de la Página
st.set_page_config(page_title="Análisis NOTAM | Flex Watch", page_icon="📜")
st.title("Análisis de NOTAMs con IA 📜")
st.markdown("Herramienta que extrae, procesa y resume NOTAMs utilizando automatización e IA.")

# --- Funciones Principales ---
def get_runways_for_airport(icao_code):
    """Busca en el DataFrame las pistas para un código ICAO y devuelve una lista."""
    if runways_df is None: return []
    airport_runways = runways_df[runways_df['airport_ident'] == icao_code]
    runway_list = []
    if not airport_runways.empty:
        runway_list.extend(airport_runways['le_ident'].dropna().tolist())
        runway_list.extend(airport_runways['he_ident'].dropna().tolist())
    return sorted(list(set(runway_list)))

def manejar_pagina_bienvenida(page, max_retries=5):
    bienvenida_locator = "button:has-text(\"I've read and understood above statements\")"
    for _ in range(max_retries):
        try:
            page.wait_for_selector(bienvenida_locator, timeout=5000)
            page.click(bienvenida_locator)
            time.sleep(2)
            if "notamSearch" in page.url: break
        except PlaywrightTimeoutError: break
        except Exception: break

def buscar_y_descargar_notams(aeropuertos):
    download_dir = os.path.join(os.getcwd(), "descargas_notam")
    os.makedirs(download_dir, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0", accept_downloads=True)
            page = context.new_page()
            page.goto("https://notams.aim.faa.gov/notamSearch/", wait_until="domcontentloaded")
            manejar_pagina_bienvenida(page)
            input_locator = "input[name='designatorsForLocation']"
            page.wait_for_selector(input_locator, timeout=12000)
            page.fill(input_locator, ", ".join(aeropuertos))
            page.press(input_locator, "Enter")
            manejar_pagina_bienvenida(page)
            page.wait_for_function("() => document.querySelectorAll('table.table.table-striped').length > 0 && document.querySelectorAll('table.table.table-striped')[0].rows.length > 1", timeout=30000)
            page.click("th:has-text('Location')")
            time.sleep(1)
            download_locator = "span.icon-excel"
            with page.expect_download() as download_info:
                page.click(download_locator)
            download = download_info.value
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_identifier = aeropuertos[0]
            copy_path = os.path.join(download_dir, f"NOTAMs_{file_identifier}_{timestamp}.xls")
            download.save_as(copy_path)
            context.close()
            browser.close()
            return copy_path
    except Exception as e:
        st.error(f"Error durante la búsqueda para {aeropuertos[0]}: {e}")
        return None

@st.cache_data(ttl=1800)
def analizar_notams_con_ia(file_content, aeropuerto_actual, runway_data_dict):
    try:
        df = pd.read_excel(file_content, skiprows=4)
        df.columns = ["Location", "NOTAM #/LTA #", "Class", "Issue Date (UTC)", "Effective Date (UTC)", "Expiration Date (UTC)", "Condition"]
        if df.empty:
            return f"✅ No se encontraron NOTAMs activos para **{aeropuerto_actual}**."
        
        datos_texto = df.to_string()
        
        runway_info_text = ""
        for airport, runways in runway_data_dict.items():
            runway_list_str = ", ".join(runways) if runways else "No encontradas"
            runway_info_text += f"* Pistas en {airport}: [{runway_list_str}]\n"

        prompt = f"""
        Eres un asistente experto en operaciones aéreas. Analiza los siguientes NOTAMs para el aeropuerto {aeropuerto_actual}.

        **Infraestructura de Pistas Disponibles:**
        {runway_info_text}

        **Datos de NOTAMs:**
        {datos_texto}

        **Tu Tarea:**
        1. Clasifica los NOTAMs por tipo (CIERRES DE PISTA, OBSTÁCULOS, RODAJE, etc.).
        2. Al analizar un cierre de pista, compáralo con la lista de pistas disponibles y especifica en tu resumen qué pistas quedan operativas.
        3. Genera un resumen final destacando solo los puntos más críticos que afecten la operación.
        4. Presenta el resultado en Markdown.
        """
        return call_ai_with_fallback(prompt, AI_MODELS)
    except Exception as e:
        return f"❌ Error al procesar el archivo Excel: {e}"

# --- Interfaz de Usuario de Streamlit ---
st.subheader("Selección de Aeropuertos")

airports_by_country = {
    "🇺🇸 Estados Unidos": ["KMIA", "KLAX", "KJFK"], "🇨🇴 Colombia": ["SKBO", "SKRG"], "🇧🇷 Brasil": ["SBFL", "SBEG", "SBKP","SBVT"],
    "🇲🇽 México": ["MMGL", "MMSM"], "🇪🇨 Ecuador": ["SEQM", "SEGU"], "🇦🇷 Argentina": ["SAEZ"],
    "🇨🇱 Chile": ["SCEL"], "🇵🇪 Perú": ["SPJC"], "🇨🇷 Costa Rica": ["MROC"],
    "🇸🇻 El Salvador": ["MSLP"], "🇺🇾 Uruguay": ["SUMU"], "🇬🇹 Guatemala": ["MGGT"],
}

selected_airports = []
countries = list(airports_by_country.keys())
num_countries = len(countries)
cols = st.columns(3)

for i in range(num_countries):
    country = countries[i]
    airports = airports_by_country[country]
    with cols[i % 3].expander(country):
        for airport in airports:
            if st.checkbox(airport, key=f"notam_{airport}"):
                selected_airports.append(airport)

st.subheader("Búsqueda Manual")
aeropuertos_str_manual = st.text_input("Ingresa códigos ICAO adicionales (separados por coma):", placeholder="Ej: SKMD, SPIM").upper()

if st.button("🚀 Descargar y Analizar", type="primary"):
    manual_airports = [code.strip() for code in aeropuertos_str_manual.split(',') if code.strip()]
    total_airports = sorted(list(set(selected_airports + manual_airports)))
    
    if not total_airports:
        st.warning("⚠️ Debes seleccionar o ingresar al menos un aeropuerto.")
    else:
        st.info(f"Iniciando análisis para {len(total_airports)} aeropuertos...")
        st.divider()

        # --- CAMBIO: Bucle para procesar cada aeropuerto individualmente ---
        for aeropuerto in total_airports:
            st.header(f"Análisis para: {aeropuerto}")
            
            runway_data = {aeropuerto: get_runways_for_airport(aeropuerto)}
            
            with st.spinner(f"🛰️ Contactando FAA y descargando NOTAMs para {aeropuerto}..."):
                # Se llama a la función de descarga para un solo aeropuerto a la vez
                archivo = buscar_y_descargar_notams([aeropuerto])
            
            if archivo:
                st.success(f"✅ Archivo de NOTAMs descargado para {aeropuerto}.")
                with st.spinner(f"🧠 Analizando datos con IA para {aeropuerto}..."):
                    with open(archivo, 'rb') as f:
                        file_content = f.read()
                    # Se llama al análisis para un solo aeropuerto
                    resumen = analizar_notams_con_ia(file_content, aeropuerto, runway_data)
                
                st.subheader("📄 Resumen de Inteligencia Artificial", anchor=False)
                st.markdown(resumen)
                
                try:
                    os.remove(archivo)
                except Exception:
                    pass
            else:
                st.error(f"❌ No se pudo completar la descarga para {aeropuerto}.")
            
            st.divider()

st.caption("Aplicación de Análisis Operacional")