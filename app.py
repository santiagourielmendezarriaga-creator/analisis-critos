import streamlit as st
import pandas as pd
import plotly.express as px
import random
from datetime import datetime

st.title("📊 Mi primer gráfico de tendencia")

# Guardar datos
if "datos" not in st.session_state:
    st.session_state.datos = []

# Botón para agregar un valor nuevo
if st.button("➕ Agregar punto a la gráfica"):
    nuevo_valor = random.randint(1, 100)
    ahora = datetime.now()
    st.session_state.datos.append({"hora": ahora, "valor": nuevo_valor})
    st.success(f"¡Valor {nuevo_valor} agregado!")

# Mostrar la gráfica si hay datos
if st.session_state.datos:
    df = pd.DataFrame(st.session_state.datos)
    fig = px.line(df, x="hora", y="valor", title="Tendencia", markers=True)
    st.plotly_chart(fig)
else:
    st.info("Haz clic en el botón para comenzar a ver la tendencia.")