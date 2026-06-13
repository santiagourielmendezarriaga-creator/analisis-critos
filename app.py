import streamlit as st
import time
from datetime import datetime

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=3)
    except:
        pass

# ==================== INICIALIZAR ESTADO ====================
if "cycle" not in st.session_state:
    st.session_state.cycle = 0
    st.session_state.balance = 1000.0
    st.session_state.position = 0.0
    st.session_state.last_action = None
    st.session_state.trades = []

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot Test - Señal Forzada", layout="wide")
st.title("🔁 Bot Test - Señal forzada cada 10 segundos")

st.sidebar.header("Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 5, 30, 10)
auto = st.sidebar.checkbox("Auto-refrescar", True)

st.sidebar.subheader("💰 Cartera")
st.sidebar.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
st.sidebar.metric("Posición BTC", f"{st.session_state.position:.6f}")
st.sidebar.metric("Operaciones", len(st.session_state.trades))

if st.sidebar.button("Reiniciar"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Alerta - Bot test")
    st.success("Enviado")

st.info("⚡ Este bot NO usa precios de mercado. Cada ciclo alterna entre COMPRA y VENTA forzadamente para verificar que la app se actualiza y envía alertas.")

# ==================== LÓGICA DE SEÑAL FORZADA ====================
st.session_state.cycle += 1
st.markdown(f"## 🔄 Ciclo actual: **{st.session_state.cycle}**")

# Alternar señal cada ciclo (si ciclo par -> BUY, impar -> SELL)
if st.session_state.cycle % 2 == 0:
    signal = "BUY"
else:
    signal = "SELL"

# Mostrar señal en grande
st.markdown(f"### 📡 Señal generada: **{'🟢 COMPRAR' if signal == 'BUY' else '🔴 VENDER'}**")

# Decidir acción según posición
action = None
if signal == "BUY" and st.session_state.position == 0:
    action = "BUY"
elif signal == "SELL" and st.session_state.position > 0:
    action = "SELL"

# Ejecutar acción simulada
if action == "BUY":
    amount = 500.0
    price = 1_000_000  # precio ficticio
    eff_price = price * 1.0005
    commission = amount * 0.001
    qty = (amount - commission) / eff_price
    st.session_state.balance -= amount
    st.session_state.position += qty
    msg = f"🟢 *COMPRA FORZADA* (ciclo {st.session_state.cycle})\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nSaldo: ${st.session_state.balance:.2f}"
    send_telegram(msg)
    st.session_state.trades.append((datetime.now(), msg))
    st.success("✅ Orden de COMPRA ejecutada (simulada)")

elif action == "SELL":
    qty = st.session_state.position
    price = 1_000_000
    eff_price = price * 0.9995
    gross = qty * eff_price
    commission = gross * 0.001
    net = gross - commission
    st.session_state.balance += net
    st.session_state.position = 0
    msg = f"🔴 *VENTA FORZADA* (ciclo {st.session_state.cycle})\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nNeto: ${net:.2f}\nSaldo: ${st.session_state.balance:.2f}"
    send_telegram(msg)
    st.session_state.trades.append((datetime.now(), msg))
    st.success("✅ Orden de VENTA ejecutada (simulada)")
else:
    st.info(f"⚠️ No se ejecutó orden porque señal {signal} no coincide con posición (pos={st.session_state.position:.6f})")

# Mostrar historial
st.subheader("📜 Historial de operaciones")
for ts, msg in reversed(st.session_state.trades[-10:]):
    st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:80]}")

st.caption(f"El ciclo aumenta cada {refresh} segundos. Si el contador no sube, la app no se actualiza.")

# Auto refresco
if auto:
    time.sleep(refresh)
    st.rerun()
