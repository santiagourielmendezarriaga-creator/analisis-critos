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

## Vigía (opcional): un agente que lee, avisa y puede re-chequear datos
Apagado por defecto. Para encenderlo, en Render → Environment pon `VIGIA=true` (necesita
Firebase y Telegram ya configurados). Con eso, dentro del mismo worker:
- Cada 30 min revisa con reglas fijas que el bot lata y que el motor v2 siga chequeando; si no,
  te avisa por Telegram (sin repetir el mismo aviso antes de 6 h).
- Una vez al día (después de las 8:00 de CDMX) te manda un resumen con cifras exactas: señales de
  24 h, compra periódica simulada y tendencia en vivo. Si hay `GROQ_API_KEY`, la IA agrega una
  "lectura" de 2-3 frases; las cifras las calcula el código, no la IA.
- **No puede operar**: no usa las llaves de Bitso, no tiene herramientas de compra/venta, no cambia
  TP, SL, umbral ni ningún parámetro, solo escribe a tu chat privado (`TELEGRAM_CHAT_ID`, nunca al
  canal) y tiene tope de 10 mensajes al día. En Firebase solo escribe en su propia ruta
  `vigia_acciones` (un registro de lo que hizo o habría hecho); el bot no la lee.
- **Una sola acción, de mantenimiento: re-chequear datos.** Si el bot está vivo pero el motor v2
  lleva más de 2 h sin chequear, o no pudo obtener velas, el vigía pide que el v2 vuelva a evaluar
  en el siguiente ciclo (no espera los 15 min y olvida la pausa tras un fallo de datos). No cambia
  cómo decide el bot. Decide un código con reglas fijas, no la IA; espera mínima de 2 h entre
  acciones y máximo 3 al día. La ejecuta el hilo del propio bot.
- `VIGIA_ACCIONES`: `sombra` (por defecto) solo anota "habría re-chequeado" en `vigia_acciones` y en
  el resumen diario, sin actuar; `activo` además lo pide y te avisa por Telegram; `no` lo desactiva.
  Recomendado: dejar `sombra` unas 2 semanas, revisar cuántas veces habría actuado y pasar a `activo`.
- Opcionales: `VIGIA_HORA_RESUMEN` (0-23, por defecto 8), `VIGIA_MINUTOS` (5-240, por defecto 30)
  y `VIGIA_USAR_IA=false` para el resumen solo con cifras.
- Si Render reinicia el servicio, el vigía puede repetir el resumen de ese día una vez.
- En los Logs deja una línea `Vigía: revisión ...` en cada vuelta (la primera, 1 min después de
  arrancar). Si no aparece, la línea `Vigía: apagado ...` dice qué falta.

## Resumen diario a un canal de Telegram (opcional)
Apagado por defecto. Una vez al día manda UN mensaje con cifras agregadas: señales enviadas y
bloqueadas por la segunda IA en 24 h, resultado observado a 1, 4 y 24 h, qué habría pasado con las
bloqueadas y el aviso de que es un simulador educativo (no es asesoría financiera, se puede perder
dinero). Lo arma el código, sin IA; no incluye saldos, llaves, posiciones ni operaciones y no dice
"probabilidad de acierto".
- `CANAL_RESUMEN=vista_previa`: lo manda **solo a tu chat privado** (`TELEGRAM_CHAT_ID`) con el
  encabezado "VISTA PREVIA". Empieza por aquí y revisa uno o dos días el texto y las cifras.
- `CANAL_RESUMEN=publicar` + `CANAL_RESUMEN_ID=@nombre_del_canal`: lo publica en el canal. El bot
  debe ser administrador del canal con permiso solo para publicar mensajes. Si `CANAL_RESUMEN_ID` no
  es válido, no publica y se queda en vista previa.
- `CANAL_RESUMEN_HORA` (0-23, por defecto 20): hora de CDMX a partir de la cual sale.
- **No es `TELEGRAM_CANAL_ID`.** Esa variable existe desde antes y hace que cada señal se mande a ese
  canal EN LUGAR de a tu chat privado (con el formato actual, que dice "Probabilidad" y no trae aviso
  legal). Para el resumen usa solo `CANAL_RESUMEN_ID`.
- En Firebase solo escribe en su propia ruta `resumen_publico` (para no repetir el mensaje del día);
  el bot no la lee. Si Render reinicia el servicio, el mensaje de ese día puede repetirse una vez.
- Mientras haya menos de 30 señales por fila, el mensaje lo avisa: las cifras no concluyen nada.

## Cosas a saber
- Render gratis puede reiniciar el servicio en cualquier momento; el estado vive en Firebase,
  así que retoma solo, con un hueco de 1 a 2 minutos.
- Solo debe haber UNA instancia del worker.
- Si el worker deja de latir 2 minutos, un panel de Streamlit abierto retoma los ciclos.
- Para dinero real, un hosting de pago que no se duerma es más seguro que este esquema.
