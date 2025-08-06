import streamlit as st
import requests
from g4f.client import Client
from datetime import datetime

# --- Lógica de Respaldo de IA ---
AI_MODELS = ["gpt-4o-mini", "gemini-2.5-flash", "grok-3", "gpt-4.1-mini"]

def call_ai_with_fallback(prompt, model_list):
    """Intenta llamar a la IA con una lista de modelos hasta que uno funcione."""
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

# --- Configuración de la Página ---
st.set_page_config(
    page_title="Análisis WX | Flex Watch",
    page_icon="🌦️"
)
st.title("Análisis Meteorológico (WX) 🌦️")
st.markdown("Herramienta para obtener y analizar TAF y METAR de estaciones aéreas.")

# --- Funciones de API y Análisis ---
@st.cache_data(ttl=600)
def obtener_taf_de_api(station_code):
    """Consulta la API de aviationweather.gov para obtener el TAF de una estación."""
    url = f"https://aviationweather.gov/api/data/taf?ids={station_code.upper()}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        if len(lines) > 1:
            full_raw_taf = " ".join(line.strip() for line in lines[1:])
            return " ".join(full_raw_taf.split())
        return None
    except requests.RequestException as e:
        st.error(f"Error de red al consultar TAF para {station_code}: {e}")
        return None

@st.cache_data(ttl=600)
def obtener_metars_de_api(station_code):
    """Consulta la API para obtener el historial de METARs de una estación."""
    url = f"https://aviationweather.gov/api/data/metar?ids={station_code.upper()}&hours=6&format=raw"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        if len(lines) > 1:
            return [line.strip() for line in lines[1:]]
        return None
    except requests.RequestException as e:
        st.error(f"Error de red al consultar METAR para {station_code}: {e}")
        return None

@st.cache_data(ttl=3600)
def analizar_taf_con_ia(raw_taf, station_code):
    """Envía el TAF a la IA para su análisis utilizando el sistema de respaldo."""
    prompt = f"Eres un meteorólogo experto. Traduce el siguiente TAF para la estación {station_code} a un resumen claro y conciso en español, explicando viento, visibilidad, nubes y cualquier cambio (TEMPO, BECMG, FM) de forma práctica sin omitir datos tecnicos. Al final entrega Notas al Piloto y despachador especificando hora de las condiciones mas adversas. (alerta si esta por debajominimos meteorologicos: 500 pies de techo)"
    full_prompt = f"{prompt}\n\nTAF CRUDO:\n{raw_taf}"
    return call_ai_with_fallback(full_prompt, AI_MODELS)

@st.cache_data(ttl=3600)
def analizar_tendencia_metar_con_ia(metar_list, station_code):
    """Envía una secuencia de METARs a la IA para analizar la tendencia utilizando el sistema de respaldo."""
    metar_history = "\n".join(metar_list)
    prompt = f"""
    Eres un meteorólogo experto. A continuación, te proporciono una secuencia cronológica de los METARs más recientes para la estación {station_code}.
    Tu tarea es analizar estos reportes y determinar la **tendencia** del clima.

    HISTORIAL DE METARs (del más reciente al más antiguo):
    {metar_history}

    1.  **Tendencia:** Por favor, responde con un resumen breve (una o dos frases) en español, (deben aparecer los datos tecnicos), indicando si las condiciones están **mejorando, empeorando o manteniéndose estables**.
        Enfócate en cambios de visibilidad, techo de nubes (BKN/OVC) y fenómenos significativos. CUANDO ESTEN MEJORANDO PON UNA FLECHA HACIA ARRIBA (⬆️), SI ESTAN EMPEORANDO PON UNA FLECHA HACIA ABAJO (⬇️) Y SI SE MANTIENEN ESTABLES PON UN SIMBOLO DE IGUAL (=).
        BRINDA UN PRONOSTICO MUY BREVE DE LO QUE SE ESPERA EN LA PROXIMA HORA.
    2.  **METAR Vigente:** Indica la información técnica del METAR más reciente (el primero de la lista), incluyendo viento, visibilidad, nubes y cualquier fenómeno significativo.
    """
    return call_ai_with_fallback(prompt, AI_MODELS)

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
            if st.checkbox(airport, key=f"wx_{airport}"):
                selected_airports.append(airport)

st.subheader("Búsqueda Manual")
station_input = st.text_input(
    "Ingrese códigos ICAO adicionales (separados por coma):",
    placeholder="Ej: SKMD, SPIM",
).upper()

if st.button("Generar Briefing", type="primary"):
    manual_airports = [code.strip() for code in station_input.split(',') if code.strip()]
    total_airports = sorted(list(set(selected_airports + manual_airports)))
    
    if not total_airports:
        st.warning("Por favor, seleccione o ingrese al menos un código de estación.")
    else:
        st.info(f"Analizando aeropuertos: {', '.join(total_airports)}")
        for station in total_airports:
            with st.expander(f"Análisis Detallado para {station}", expanded=True):
                export_content = []
                st.markdown("##### 📈 Tendencia Reciente (METAR)")
                metar_list = obtener_metars_de_api(station)
                if metar_list:
                    metar_summary = analizar_tendencia_metar_con_ia(tuple(metar_list), station)
                    st.markdown(metar_summary)
                    export_content.append(f"--- TENDENCIA RECIENTE (METAR) ---\n{metar_summary}\n")
                    with st.popover("Ver METARs crudos"):
                        st.code("\n".join(metar_list), language="text")
                else:
                    st.warning("No se encontró historial de METAR.")
                    export_content.append("--- TENDENCIA RECIENTE (METAR) ---\nNo se encontró historial de METAR.\n")

                st.markdown("---")
                st.markdown("##### ✈️ Pronóstico a Futuro (TAF)")
                raw_taf = obtener_taf_de_api(station)
                if raw_taf:
                    taf_summary = analizar_taf_con_ia(raw_taf, station)
                    st.markdown(taf_summary)
                    export_content.append(f"\n--- PRONÓSTICO A FUTURO (TAF) ---\n{taf_summary}\n")
                    with st.popover("Ver TAF crudo"):
                        st.code(raw_taf, language="text")
                else:
                    st.warning("No se encontró TAF.")
                    export_content.append("\n--- PRONÓSTICO A FUTURO (TAF) ---\nNo se encontró TAF.\n")
                
                st.markdown("---")
                final_export_text = "\n".join(export_content)
                now = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = f"Briefing_{station}_{now}.txt"
                st.download_button(
                    label="📄 Exportar a TXT",
                    data=final_export_text.encode('utf-8'),
                    file_name=file_name,
                    mime="text/plain"
                )