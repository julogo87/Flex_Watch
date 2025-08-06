import streamlit as st

st.set_page_config(
    page_title="FLEX WATCH | Dashboard",
    page_icon="✈️",
    layout="wide"
)
# --- AÑADIR EL LOGO A LA BARRA LATERAL ---
# Usa la ruta a tu archivo de imagen
st.sidebar.image("assets/logo.png")
# --- FIN DEL CÓDIGO DEL LOGO ---
st.title("FLEX WATCH Dashboard ✈️")

st.sidebar.success("Selecciona una de las páginas de análisis.")

st.markdown(
    """
    ### ¡Bienvenido a tu dashboard de análisis operacional!
    
    Esta es una herramienta interactiva creada para ayudarte a monitorear
    diferentes aspectos de la operación.
    
    **👈 Por favor, selecciona un análisis del menú a la izquierda** para comenzar.
    
    - **Análisis WX:** Visualiza y analiza datos meteorológicos (METAR/TAF) con ayuda de IA.
    - **Análisis Notam:** Procesa y analiza los NOTAMs relevantes.
    - **Operation Health Check:** Analiza WX y NOTAM de cara a la Operación.
    """
)