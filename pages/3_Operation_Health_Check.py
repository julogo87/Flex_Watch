import streamlit as st
import pandas as pd
import io
import os
import importlib
from datetime import datetime
from fpdf import FPDF
from g4f.client import Client
import airportsdata
import streamlit.components.v1 as components

# --- Cargar la base de datos de pistas al iniciar ---
@st.cache_resource
def load_runway_data():
    """Carga el archivo runways.csv en un DataFrame de Pandas."""
    try:
        runway_path = os.path.join("assets", "runways.csv")
        return pd.read_csv(runway_path)
    except FileNotFoundError:
        st.error("Error: No se encontró el archivo `runways.csv` en la carpeta `assets`.")
        st.error("Por favor, descárgalo desde https://ourairports.com/data/ y colócalo en la carpeta `assets`.")
        return None

runways_df = load_runway_data()

# Cargar datos de aeropuertos para conversión
try:
    airports = airportsdata.load('IATA')
except Exception as e:
    st.error(f"No se pudo cargar la base de datos de aeropuertos: {e}")
    st.stop()

# Reutilizando funciones de otras páginas
try:
    wx_page = importlib.import_module("pages.1_Analisis_WX")
    notam_page = importlib.import_module("pages.2_Analisis_Notam")
    obtener_taf_de_api = wx_page.obtener_taf_de_api
    buscar_y_descargar_notams = notam_page.buscar_y_descargar_notams
    analizar_notams_raw = notam_page.analizar_notams_con_ia
except ImportError:
    st.error("Asegúrate de que los archivos `pages/1_Analisis_WX.py` y `pages/2_Analisis_Notam.py` existan.")
    st.stop()

# Configuración de la Página
st.set_page_config(page_title="Operation Health Check | Flex Watch", page_icon="🩺", layout="wide")
st.title("🩺 Operation Health Check")
st.markdown("Pega tu itinerario para analizar el impacto de WX y NOTAMs en cada vuelo, ahora con información de pistas.")

# --- Funciones de la Página ---

class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, 'Briefing Operacional', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def create_report_pdf(df_report):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font('Helvetica', 'B', 16)
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.cell(0, 10, f"Análisis de Itinerario - {report_date}", 0, 1, 'L')
    pdf.set_font('Helvetica', 'I', 10)
    pdf.cell(0, 10, "(Todas las horas en UTC)", 0, 1, 'L')
    pdf.ln(10)

    for _, row in df_report.iterrows():
        pdf.set_font('Helvetica', 'B', 12)
        flight_title = f"Vuelo: {row['Flight']} ({row['From_IATA']} -> {row['To_IATA']})"
        pdf.cell(0, 10, flight_title, 0, 1)

        pdf.set_font('Helvetica', '', 10)
        metrics_text = (
            f"Matrícula: {row['Reg.'] or 'N/A'}  |  "
            f"STD (UTC): {str(row['STD']).split(' ')[-1] if ' ' in str(row['STD']) else str(row['STD'])}  |  "
            f"STA (UTC): {str(row['STA']).split(' ')[-1] if ' ' in str(row['STA']) else str(row['STA'])}"
        )
        pdf.cell(0, 10, metrics_text, 0, 1)

        pdf.set_font('Helvetica', '', 10)
        analysis_text = row['AI_Analysis'].encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 5, analysis_text)
        
        pdf.ln(5)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
        pdf.ln(5)

    return pdf.output(dest='S').encode('latin-1')

def get_runways_for_airport(icao_code):
    """Busca en el DataFrame las pistas para un código ICAO y devuelve una lista."""
    if runways_df is None or icao_code == "NO ENCONTRADO":
        return []
    
    airport_runways = runways_df[runways_df['airport_ident'] == icao_code]
    
    runway_list = []
    if not airport_runways.empty:
        runway_list.extend(airport_runways['le_ident'].dropna().tolist())
        runway_list.extend(airport_runways['he_ident'].dropna().tolist())
        
    return sorted(list(set(runway_list)))

def iata_to_icao(iata_code):
    if pd.isna(iata_code) or iata_code == '': return ''
    try: return airports[str(iata_code).strip().upper()]['icao']
    except KeyError: return "NO ENCONTRADO"

AI_MODELS = ["gpt-4o-mini", "gemini-2.5-flash", "grok-3", "gpt-4.1-mini"]

def call_ai_with_fallback(prompt, model_list):
    for model in model_list:
        try:
            if model != model_list[0]: print(f"INFO: Reintentando con {model}...")
            client = Client()
            response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            raise Exception("Respuesta de IA vacía.")
        except Exception as e:
            print(f"Modelo {model} falló con error: {e}")
            continue
    return "❌ Todos los modelos de IA fallaron."

@st.cache_data(ttl=1800)
def analyze_flight_health(flight_info, taf_origin, taf_dest, notams_origin, notams_dest, runways_origin, runways_dest):
    runways_origin_str = ", ".join(runways_origin) if runways_origin else "No disponibles"
    runways_dest_str = ", ".join(runways_dest) if runways_dest else "No disponibles"
    
    prompt = f"""
    Actúa como un despachador de vuelos experto y un meteorólogo. Tu tarea es analizar el siguiente vuelo y determinar su 'estado de salud/condiciones' operacionales relevantes. Todas las horas proporcionadas (STD, STA, TAF, NOTAM) están en formato UTC.

    **Datos del Vuelo:**
    * Vuelo: {flight_info['Flight']}
    * Ruta: {flight_info['From_ICAO']} ({flight_info['From_IATA']}) -> {flight_info['To_ICAO']} ({flight_info['To_IATA']})
    * Matrícula (Reg.): {flight_info['Reg.']}
    * Hora de Salida (STD UTC): {flight_info['STD']}
    * Hora de Llegada (STA UTC): {flight_info['STA']}

    **Infraestructura de Pistas:**
    * Pistas Disponibles en Origen ({flight_info['From_ICAO']}): [{runways_origin_str}]
    * Pistas Disponibles en Destino ({flight_info['To_ICAO']}): [{runways_dest_str}]

    **Datos Meteorológicos (TAF UTC):**
    * TAF Origen ({flight_info['From_ICAO']}): {taf_origin or "No disponible"}
    * TAF Destino ({flight_info['To_ICAO']}): {taf_dest or "No disponible"}

    **Datos NOTAM (Resumen IA UTC):**
    * NOTAMs Origen ({flight_info['From_ICAO']}): {notams_origin or "No disponibles"}
    * NOTAMs Destino ({flight_info['To_ICAO']}): {notams_dest or "No disponibles"}

    **Tu Análisis:**
    1.  **Análisis WX:** ¿El TAF del origen o destino muestra condiciones adversas cerca de las horas de operación?
    2.  **Análisis NOTAM y Pistas:** Basado en la lista de pistas disponibles, si un NOTAM menciona un cierre de pista, determina el impacto real. ¿Quedan pistas operativas? ¿Son adecuadas? Menciona qué pistas quedan disponibles.
    3.  **Conclusión:** Proporciona un resumen conciso (máximo 3-4 frases) del estado del vuelo. Clasifícalo con un emoji y una palabra clave al inicio de tu respuesta: `✅ Normal`, `⚠️ Monitorear`, o `❌ En Riesgo`.
    """
    return call_ai_with_fallback(prompt, AI_MODELS)

# --- Interfaz de Usuario ---
st.header("1. Pega tu Itinerario Aquí")
st.info("Haz clic en la primera celda y pega los datos (Ctrl+V). Asegúrate de que todas las horas estén en formato UTC.")

df_template = pd.DataFrame([{"Order": "","Flight": "","Date": "","ST": "","State": "","STD": "","STA": "","Best DT": "","Best AT": "","From": "","To": "","Reg.": "","Own / Sub": "","Delay": "","Pax(F/C/Y)": ""}])
edited_df = st.data_editor(df_template, num_rows="dynamic", use_container_width=True, key="itinerary_editor")

if 'analysis_df' not in st.session_state:
    st.session_state.analysis_df = None

if st.button("🩺 Analizar Salud del Itinerario", type="primary"):
    df_itinerary = edited_df.dropna(how='all').reset_index(drop=True)
    if 'Flight' not in df_itinerary.columns or pd.isna(df_itinerary['Flight'].iloc[0]) or df_itinerary['Flight'].iloc[0] == '':
        st.warning("⚠️ La tabla está vacía o no tiene vuelos.")
    else:
        st.header("2. Itinerario Identificado y Convertido a ICAO")
        df_itinerary['From_IATA'] = df_itinerary['From']
        df_itinerary['To_IATA'] = df_itinerary['To']
        df_itinerary['From_ICAO'] = df_itinerary['From_IATA'].apply(iata_to_icao)
        df_itinerary['To_ICAO'] = df_itinerary['To_IATA'].apply(iata_to_icao)
        st.dataframe(df_itinerary[['Order', 'Flight', 'From_IATA', 'To_IATA', 'From_ICAO', 'To_ICAO', 'STD', 'STA']], use_container_width=True)

        with st.spinner("Optimizando... Obteniendo todos los NOTAMs necesarios..."):
            all_airports_icao = pd.concat([df_itinerary['From_ICAO'], df_itinerary['To_ICAO']]).unique()
            notam_summaries = {}
            for airport_icao in all_airports_icao:
                if airport_icao and airport_icao != "NO ENCONTRADO":
                    file_path = buscar_y_descargar_notams([airport_icao])
                    if file_path and os.path.exists(file_path):
                        with open(file_path, 'rb') as f: file_content = f.read()
                        notam_summaries[airport_icao] = analizar_notams_raw(file_content, airport_icao)
                        os.remove(file_path)
                    else: notam_summaries[airport_icao] = "No se pudieron obtener los NOTAMs."
        st.success("Todos los NOTAMs han sido recopilados y pre-analizados.")

        progress_bar = st.progress(0, text="Analizando vuelos...")
        results = []
        total_flights = len(df_itinerary)
        for index, row in df_itinerary.iterrows():
            origin_icao, dest_icao = row['From_ICAO'], row['To_ICAO']
            runways_origin = get_runways_for_airport(origin_icao)
            runways_dest = get_runways_for_airport(dest_icao)
            taf_origin = obtener_taf_de_api(origin_icao) if origin_icao != "NO ENCONTRADO" else "Código ICAO no válido"
            taf_dest = obtener_taf_de_api(dest_icao) if dest_icao != "NO ENCONTRADO" else "Código ICAO no válido"
            notams_origin = notam_summaries.get(origin_icao, "No disponible")
            notams_dest = notam_summaries.get(dest_icao, "No disponible")
            ai_summary = analyze_flight_health(row, taf_origin, taf_dest, notams_origin, notams_dest, runways_origin, runways_dest)
            results.append(ai_summary)
            progress_text = f"Analizando vuelo {row['Flight']} ({row['From_IATA']}-{row['To_IATA']})... [{index+1}/{total_flights}]"
            progress_bar.progress((index + 1) / total_flights, text=progress_text)
        progress_bar.empty()

        st.header("3. Resultados del Health Check")
        df_itinerary['AI_Analysis'] = results
        st.session_state.analysis_df = df_itinerary.copy()

        for index, row in st.session_state.analysis_df.iterrows():
            st.subheader(f"✈️ Vuelo: {row['Flight']} ({row['From_IATA']} → {row['To_IATA']})", anchor=False)
            col1, col2, col3 = st.columns(3)
            col1.metric("Matrícula (Reg.)", value=row['Reg.'] or "N/A")
            col2.metric("Hora Salida (STD UTC)", value=str(row['STD']).split(' ')[-1] if ' ' in str(row['STD']) else str(row['STD']))
            col3.metric("Hora Llegada (STA UTC)", value=str(row['STA']).split(' ')[-1] if ' ' in str(row['STA']) else str(row['STA']))
            st.markdown(row['AI_Analysis'])
            st.divider()

# --- Sección de Exportación / Impresión ---
if st.session_state.analysis_df is not None and not st.session_state.analysis_df.empty:
    st.header("4. Acciones", anchor=False)
    
    col1, col2 = st.columns(2)

    with col1:
        pdf_data = create_report_pdf(st.session_state.analysis_df)
        st.download_button(
            label="📄 Descargar Reporte en PDF",
            data=pdf_data,
            file_name=f"Reporte_Salud_Operacional_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    with col2:
        # --- CAMBIO: Botón de Imprimir Corregido ---
        # Usamos un botón de Streamlit normal que, al ser presionado, inyecta
        # el código JavaScript para abrir el diálogo de impresión.
        if st.button("🖨️ Imprimir Reporte", use_container_width=True):
            components.html(
                "<script>window.print();</script>",
                height=0,
            )