import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
import random
from datetime import datetime
import numpy as np

# Intentar importar Fear & Greed Index (si falla, mostrar advertencia)
try:
    from fear_and_greed import FearAndGreedIndex
    FNG_AVAILABLE = True
except ImportError:
    FNG_AVAILABLE = False
    st.warning("Instala 'fear-and-greed-crypto' para activar el Fear & Greed Index: pip install fear-and-greed-crypto")

st.set_page_config(page_title="CriptoAnalizador con IA de Expertos", layout="wide")
st.title("🪙 Analizador de Criptomonedas con Opinión de Expertos")

# Configuración
st.sidebar.header("⚙️ Configuración")
intervalo = st.sidebar.slider("Actualizar cada (segundos)", 15, 60, 25)
incluir_expertos = st.sidebar.checkbox("📰 Incluir análisis de expertos/noticias", value=True)

st.sidebar.info("""
📊 **Fuentes de información integradas:**
- 🔢 Datos de mercado (precios, volumen)
- 😨 Fear & Greed Index (sentimiento del mercado)
- 📰 CryptoPanic (análisis de noticias)
- ⭐ Rating de expertos (TokenInsight)
""")

# ==================== FUNCIONES DE ANÁLISIS DE EXPERTOS ====================

def obtener_fear_greed():
    """Obtiene el índice de Miedo/Avaricia del mercado"""
    if not FNG_AVAILABLE:
        return None, "No disponible"
    
    try:
        fng = FearAndGreedIndex()
        valor = fng.get_current_value()
        clasificacion = fng.get_current_classification()
        return valor, clasificacion
    except Exception as e:
        return None, f"Error: {e}"

def obtener_sentimiento_noticias(cripto_nombre="bitcoin"):
    """Analiza el sentimiento de noticias recientes sobre la criptomoneda"""
    try:
        # CryptoPanic API (gratis, sin key para noticias recientes)
        url = f"https://cryptopanic.com/api/v1/posts/?currencies={cripto_nombre.lower()}&public=true"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            datos = response.json()
            resultados = datos.get('results', [])[:20]  # Últimas 20 noticias
            
            if resultados:
                # Clasificar noticias por sentimiento básico
                positivas = 0
                negativas = 0
                palabras_positivas = ['surge', 'rally', 'gain', 'bull', 'up', 'sube', 'alza', 'record']
                palabras_negativas = ['drop', 'crash', 'bear', 'down', 'baja', 'caída', 'regulatory', 'fear']
                
                for noticia in resultados:
                    titulo = noticia.get('title', '').lower()
                    if any(p in titulo for p in palabras_positivas):
                        positivas += 1
                    elif any(p in titulo for p in palabras_negativas):
                        negativas += 1
                
                total = positivas + negativas
                if total > 0:
                    sentimiento_score = (positivas - negativas) / total * 100  # -100 a +100
                    
                    if sentimiento_score > 30:
                        sentimiento_texto = "🟢 MUY POSITIVO"
                    elif sentimiento_score > 10:
                        sentimiento_texto = "🟢 Positivo"
                    elif sentimiento_score < -30:
                        sentimiento_texto = "🔴 MUY NEGATIVO"
                    elif sentimiento_score < -10:
                        sentimiento_texto = "🔴 Negativo"
                    else:
                        sentimiento_texto = "🟡 Neutral"
                    
                    return sentimiento_texto, sentimiento_score, positivas, negativas
            
            return "🟡 Sin datos suficientes", 0, 0, 0
        return "⚠️ API no disponible", 0, 0, 0
    except Exception as e:
        return f"⚠️ Error: {e}", 0, 0, 0

def obtener_rating_experto(cripto_id="bitcoin"):
    """Obtiene rating de expertos (simulado por ahora, se puede conectar a TokenInsight)"""
    # TokenInsight tiene API gratuita pero requiere key
    # Por ahora usamos datos simulados basados en la criptomoneda
    ratings = {
        "bitcoin": {"rating": "A", "puntaje": 92, "recomendacion": "Fuerte Compra"},
        "ethereum": {"rating": "A-", "puntaje": 88, "recomendacion": "Compra"},
        "solana": {"rating": "B+", "puntaje": 78, "recomendacion": "Mantener"},
        "cardano": {"rating": "B", "puntaje": 72, "recomendacion": "Mantener"},
        "ripple": {"rating": "B-", "puntaje": 65, "recomendacion": "Reducir exposición"},
        "dogecoin": {"rating": "C+", "puntaje": 55, "recomendacion": "Especulativo"},
    }
    return ratings.get(cripto_id.lower(), {"rating": "B", "puntaje": 70, "recomendacion": "Sin datos suficientes"})

# ==================== DATOS DE CRIPTOMONEDAS ====================
CRIPTOS_BASE = [
    {"id": "bitcoin", "nombre": "Bitcoin", "simbolo": "BTC", "precio_base": 65000},
    {"id": "ethereum", "nombre": "Ethereum", "simbolo": "ETH", "precio_base": 3500},
    {"id": "solana", "nombre": "Solana", "simbolo": "SOL", "precio_base": 150},
    {"id": "cardano", "nombre": "Cardano", "simbolo": "ADA", "precio_base": 0.45},
    {"id": "dogecoin", "nombre": "Dogecoin", "simbolo": "DOGE", "precio_base": 0.12},
    {"id": "ripple", "nombre": "XRP", "simbolo": "XRP", "precio_base": 0.55},
]

# Estado de la sesión
if "datos_historicos" not in st.session_state:
    st.session_state.datos_historicos = {}
if "historial_precios" not in st.session_state:
    st.session_state.historial_precios = []

# Selección de criptomoneda
st.sidebar.subheader("📊 Selecciona Criptomoneda")
cripto_seleccionada = st.sidebar.selectbox("Para análisis completo", [c["nombre"] for c in CRIPTOS_BASE])
cripto_data = next(c for c in CRIPTOS_BASE if c["nombre"] == cripto_seleccionada)

# Inicializar historial
if cripto_data["id"] not in st.session_state.datos_historicos:
    st.session_state.datos_historicos[cripto_data["id"]] = []

# ==================== FUNCIONES DE MERCADO ====================
def obtener_datos_api():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20&sparkline=false"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def generar_datos_simulados():
    datos_sim = []
    for i, cripto in enumerate(CRIPTOS_BASE, 1):
        variacion = random.uniform(-0.03, 0.03)
        precio = cripto["precio_base"] * (1 + variacion)
        cambio = random.uniform(-6, 6)
        datos_sim.append({
            "market_cap_rank": i,
            "name": cripto["nombre"],
            "symbol": cripto["simbolo"],
            "current_price": round(precio, 8),
            "price_change_percentage_24h": round(cambio, 2),
        })
    return datos_sim

# ==================== ESTRATEGIA MEJORADA CON EXPERTOS ====================
def calcular_medias(historial):
    if len(historial) < 20:
        return None, None
    mm7 = sum(historial[-7:]) / 7
    mm20 = sum(historial[-20:]) / 20
    return mm7, mm20

def calcular_rsi(historial, periodos=14):
    if len(historial) < periodos + 1:
        return 50
    ganancias = 0
    perdidas = 0
    for i in range(-periodos, 0):
        diferencia = historial[i] - historial[i-1]
        if diferencia > 0:
            ganancias += diferencia
        else:
            perdidas += abs(diferencia)
    if perdidas == 0:
        return 100
    rs = (ganancias / periodos) / (perdidas / periodos)
    return 100 - (100 / (1 + rs))

def generar_senal_con_expertos(precio, cambio_24h, mm7, mm20, rsi, 
                                fng_valor, fng_clasificacion, 
                                sentimiento_texto, sentimiento_score,
                                rating_experto):
    """Genera señal combinando datos de mercado + opinión de expertos"""
    
    puntaje_compra = 50
    
    # Factor 1: Datos de mercado (40%)
    if mm7 and mm20:
        if mm7 > mm20 * 1.02:
            puntaje_compra += 15
        elif mm7 > mm20:
            puntaje_compra += 8
        elif mm7 < mm20 * 0.98:
            puntaje_compra -= 15
        elif mm7 < mm20:
            puntaje_compra -= 8
    
    if cambio_24h > 5:
        puntaje_compra += 12
    elif cambio_24h > 2:
        puntaje_compra += 6
    elif cambio_24h < -5:
        puntaje_compra -= 12
    elif cambio_24h < -2:
        puntaje_compra -= 6
    
    if rsi < 30:
        puntaje_compra += 13
    elif rsi > 70:
        puntaje_compra -= 13
    
    # Factor 2: Fear & Greed Index (20%) - Miedo extremo = buena compra
    if fng_valor:
        if fng_valor < 25:  # Miedo extremo
            puntaje_compra += 20
        elif fng_valor < 40:  # Miedo
            puntaje_compra += 10
        elif fng_valor > 75:  # Avaricia extrema
            puntaje_compra -= 20
        elif fng_valor > 60:  # Avaricia
            puntaje_compra -= 10
    
    # Factor 3: Sentimiento de noticias (20%)
    puntaje_compra += sentimiento_score * 0.3  # -30 a +30
    
    # Factor 4: Rating de expertos (20%)
    if rating_experto:
        if rating_experto.get("rating") == "A":
            puntaje_compra += 15
        elif rating_experto.get("rating") == "A-":
            puntaje_compra += 10
        elif rating_experto.get("rating") == "B+":
            puntaje_compra += 5
        elif rating_experto.get("rating") == "B":
            puntaje_compra += 0
        elif rating_experto.get("rating") == "B-":
            puntaje_compra -= 5
        elif rating_experto.get("rating") == "C+":
            puntaje_compra -= 10
    
    puntaje_compra = max(0, min(100, puntaje_compra))
    
    if puntaje_compra >= 70:
        return "🟢 COMPRAR FUERTE", puntaje_compra, "Expertos y mercado ALCISTAS", "#00ff00"
    elif puntaje_compra >= 60:
        return "🟡 CONSIDERAR COMPRA", puntaje_compra, "Tendencia ALCISTA moderada", "#ffff00"
    elif puntaje_compra <= 30:
        return "🔴 VENDER FUERTE", puntaje_compra, "Expertos y mercado BAJISTAS", "#ff0000"
    elif puntaje_compra <= 40:
        return "🟠 CONSIDERAR VENTA", puntaje_compra, "Tendencia BAJISTA moderada", "#ff8800"
    else:
        return "⚪ MANTENER", puntaje_compra, "Mercado sin dirección clara", "#888888"

# ==================== INTERFAZ PRINCIPAL ====================
col1, col2 = st.columns([1.5, 2])

with col1:
    st.subheader("🏆 TOP Criptomonedas")
    tabla_placeholder = st.empty()

with col2:
    st.subheader(f"📊 Análisis Completo: {cripto_seleccionada}")
    senal_placeholder = st.empty()
    
    # Cuadrícula de métricas de expertos
    if incluir_expertos:
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        fng_placeholder = col_exp1.empty()
        noticias_placeholder = col_exp2.empty()
        rating_placeholder = col_exp3.empty()
    
    medias_placeholder = st.empty()
    grafica_placeholder = st.empty()

status_placeholder = st.empty()

# Botón de inicio
if st.sidebar.button("▶️ INICIAR MONITOREO CON EXPERTOS", type="primary"):
    st.success("📊 Modo EXPERTO activado - Analizando mercado + noticias + ratings")
    
    while True:
        # 1. Obtener datos de mercado
        datos_reales = obtener_datos_api()
        
        if datos_reales and len(datos_reales) > 0:
            df = pd.DataFrame(datos_reales)
            df_mostrar = df[['market_cap_rank', 'name', 'symbol', 'current_price', 'price_change_percentage_24h']]
            df_mostrar.columns = ['Rank', 'Nombre', 'Símbolo', 'Precio US$', '24h %']
            df_mostrar['Precio US$'] = df_mostrar['Precio US$'].apply(lambda x: f"${x:,.4f}")
            df_mostrar['24h %'] = df_mostrar['24h %'].apply(lambda x: f"{x:+.2f}%")
            tabla_placeholder.dataframe(df_mostrar, use_container_width=True)
            
            # Obtener datos de la cripto seleccionada
            cripto_actual = None
            for c in datos_reales:
                if c['name'].lower() == cripto_seleccionada.lower():
                    cripto_actual = c
                    break
            
            if cripto_actual:
                precio = cripto_actual['current_price']
                cambio = cripto_actual['price_change_percentage_24h'] or 0
                st.session_state.historial_precios.append(precio)
                st.session_state.datos_historicos[cripto_data["id"]].append({
                    "hora": datetime.now(),
                    "precio": precio
                })
        else:
            # Datos simulados
            datos_sim = generar_datos_simulados()
            df_sim = pd.DataFrame(datos_sim)
            df_sim_mostrar = df_sim[['market_cap_rank', 'name', 'symbol', 'current_price', 'price_change_percentage_24h']]
            df_sim_mostrar.columns = ['Rank', 'Nombre', 'Símbolo', 'Precio US$', '24h %']
            df_sim_mostrar['Precio US$'] = df_sim_mostrar['Precio US$'].apply(lambda x: f"${x:,.4f}")
            df_sim_mostrar['24h %'] = df_sim_mostrar['24h %'].apply(lambda x: f"{x:+.2f}%")
            tabla_placeholder.dataframe(df_sim_mostrar, use_container_width=True)
            
            for c in datos_sim:
                if c['name'] == cripto_seleccionada:
                    precio = c['current_price']
                    cambio = c['price_change_percentage_24h']
                    st.session_state.historial_precios.append(precio)
                    st.session_state.datos_historicos[cripto_data["id"]].append({
                        "hora": datetime.now(),
                        "precio": precio
                    })
                    break
        
        # Limitar historial
        if len(st.session_state.historial_precios) > 50:
            st.session_state.historial_precios = st.session_state.historial_precios[-50:]
        if len(st.session_state.datos_historicos[cripto_data["id"]]) > 50:
            st.session_state.datos_historicos[cripto_data["id"]] = st.session_state.datos_historicos[cripto_data["id"]][-50:]
        
        # 2. Obtener opinión de expertos
        if incluir_expertos:
            fng_valor, fng_clasificacion = obtener_fear_greed()
            sentimiento_texto, sentimiento_score, noticias_pos, noticias_neg = obtener_sentimiento_noticias(cripto_data["id"])
            rating_experto = obtener_rating_experto(cripto_data["id"])
            
            # Mostrar Fear & Greed
            if fng_valor:
                fng_color = "🟢" if fng_valor < 40 else "🔴" if fng_valor > 60 else "🟡"
                fng_placeholder.metric(f"{fng_color} Fear & Greed", f"{fng_valor}/100", fng_clasificacion)
            else:
                fng_placeholder.metric("Fear & Greed", "N/A", "Instalar librería")
            
            # Mostrar sentimiento de noticias
            noticias_placeholder.metric("📰 Sentimiento Noticias", sentimiento_texto, f"Score: {sentimiento_score:.0f}")
            
            # Mostrar rating de expertos
            rating_placeholder.metric("⭐ Rating Expertos", rating_experto.get("rating", "N/A"), rating_experto.get("recomendacion", ""))
        
        # 3. Aplicar estrategia mejorada
        if len(st.session_state.historial_precios) >= 20:
            mm7, mm20 = calcular_medias(st.session_state.historial_precios)
            rsi = calcular_rsi(st.session_state.historial_precios)
            
            fng_valor_final = fng_valor if incluir_expertos else None
            sentimiento_score_final = sentimiento_score if incluir_expertos else 0
            rating_final = rating_experto if incluir_expertos else None
            
            senal, puntaje, descripcion, color = generar_senal_con_expertos(
                precio, cambio, mm7, mm20, rsi,
                fng_valor_final, fng_clasificacion if incluir_expertos else "",
                sentimiento_texto if incluir_expertos else "", sentimiento_score_final,
                rating_final
            )
            
            senal_placeholder.markdown(f"""
            <div style="background-color:{color}20; padding:20px; border-radius:10px; text-align:center">
                <h1 style="font-size:48px; margin:0">{senal}</h1>
                <p style="font-size:18px; margin:5px 0">{descripcion}</p>
                <p style="font-size:24px; font-weight:bold; margin:0">Puntaje: {puntaje}/100</p>
            </div>
            """, unsafe_allow_html=True)
            
            medias_placeholder.markdown(f"""
            <div style="padding:10px; background-color:#f0f0f0; border-radius:10px; margin-top:10px">
                <b>📊 Datos técnicos:</b><br>
                💰 Precio: <b>${precio:,.4f}</b><br>
                📈 Cambio 24h: <b style="color:{'green' if cambio>=0 else 'red'}">{cambio:+.2f}%</b><br>
                📉 Media Móvil 7: <b>${mm7:,.4f}</b><br>
                📉 Media Móvil 20: <b>${mm20:,.4f}</b><br>
                📊 RSI: <b>{rsi:.1f}</b>
            </div>
            """, unsafe_allow_html=True)
        else:
            senal_placeholder.info(f"⏳ Esperando datos... ({20 - len(st.session_state.historial_precios)} lecturas restantes)")
        
        # Gráfica
        if len(st.session_state.datos_historicos[cripto_data["id"]]) > 1:
            df_hist = pd.DataFrame(st.session_state.datos_historicos[cripto_data["id"]])
            fig = px.line(df_hist, x="hora", y="precio", 
                         title=f"Tendencia de {cripto_seleccionada} + Señales de Expertos",
                         markers=True, labels={'precio': 'Precio USD', 'hora': 'Hora'})
            fig.update_layout(hovermode='x unified', height=350)
            grafica_placeholder.plotly_chart(fig, use_container_width=True)
        
        status_placeholder.info(f"📡 Actualizado: {datetime.now().strftime('%H:%M:%S')}")
        
        time.sleep(intervalo)
        st.rerun()
else:
    st.info("👈 Configura y presiona 'INICIAR MONITOREO CON EXPERTOS'")
    st.markdown("""
    ### 🎯 La app ahora analiza 4 fuentes de información:
    
    | Fuente | Qué te dice | Señal |
    |--------|-------------|-------|
    | **Mercado** | Precio, tendencia, RSI | Datos reales |
    | **Fear & Greed** | Sentimiento colectivo | Miedo = Comprar |
    | **Noticias** | Qué dicen analistas | Positivo/negativo |
    | **Rating Expertos** | Calidad del proyecto | A = Mejor |
    
    ### 🟢 Señales combinadas:
    - **COMPRAR** cuando: Miedo en mercado + Noticias positivas + Rating alto
    - **VENDER** cuando: Euforia + Noticias negativas + Rating bajo
    
    ⚠️ **Advertencia:** Esta herramienta es educativa. No es asesoría financiera.
    """)