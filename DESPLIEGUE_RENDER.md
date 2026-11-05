# Bot en Render (sin pestaña abierta)

`worker.py` ejecuta el mismo `app.py` en un servidor, sin pantalla. El panel de Streamlit
sigue sirviendo para ver resultados y pausar; mientras el worker late (Firebase `worker`),
el panel NO ejecuta ciclos, así no se duplican señales ni órdenes.

## Pasos
1. En Render: **New → Blueprint** (o **Web Service**) y conecta este repositorio.
   Comando de build: `pip install -r requirements-worker.txt`. Comando de inicio: `python worker.py`.
2. Plan **Free**. En **Environment** captura las variables de `render.yaml` con los MISMOS
   valores que tienes en los Secrets de Streamlit (incluida `FIREBASE_RUTA`, la nueva).
   Déjalo con `MODO_REAL=false` y `OPERAR_AUTOMATICO=false` hasta tener evidencia de las señales.
3. Cuando el despliegue termine, abre `https://TU-SERVICIO.onrender.com/health`: debe decir `ok`.
4. En UptimeRobot crea un monitor HTTP(s) a esa dirección, cada 5 minutos.
5. Comprueba en Telegram/Firebase que el bot avanza (el nodo `worker` se actualiza cada ~30 s).

## Vigía (opcional): un agente que solo lee y avisa
Apagado por defecto. Para encenderlo, en Render → Environment pon `VIGIA=true` (necesita
Firebase y Telegram ya configurados). Con eso, dentro del mismo worker:
- Cada 30 min revisa con reglas fijas que el bot lata y que el motor v2 siga chequeando; si no,
  te avisa por Telegram (sin repetir el mismo aviso antes de 6 h).
- Una vez al día (después de las 8:00 de CDMX) te manda un resumen con cifras exactas: señales de
  24 h, compra periódica simulada y tendencia en vivo. Si hay `GROQ_API_KEY`, la IA agrega una
  "lectura" de 2-3 frases; las cifras las calcula el código, no la IA.
- **No puede operar**: no escribe en Firebase, no usa las llaves de Bitso, no tiene herramientas de
  compra/venta, solo escribe a tu chat privado (`TELEGRAM_CHAT_ID`, nunca al canal) y tiene tope
  de 10 mensajes al día.
- Opcionales: `VIGIA_HORA_RESUMEN` (0-23, por defecto 8), `VIGIA_MINUTOS` (5-240, por defecto 30)
  y `VIGIA_USAR_IA=false` para el resumen solo con cifras.
- Si Render reinicia el servicio, el vigía puede repetir el resumen de ese día una vez.
- En los Logs deja una línea `Vigía: revisión ...` en cada vuelta (la primera, 1 min después de
  arrancar). Si no aparece, la línea `Vigía: apagado ...` dice qué falta.

## Cosas a saber
- Render gratis puede reiniciar el servicio en cualquier momento; el estado vive en Firebase,
  así que retoma solo, con un hueco de 1 a 2 minutos.
- Solo debe haber UNA instancia del worker.
- Si el worker deja de latir 2 minutos, un panel de Streamlit abierto retoma los ciclos.
- Para dinero real, un hosting de pago que no se duerma es más seguro que este esquema.
