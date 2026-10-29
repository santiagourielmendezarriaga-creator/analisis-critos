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

## Cosas a saber
- Render gratis puede reiniciar el servicio en cualquier momento; el estado vive en Firebase,
  así que retoma solo, con un hueco de 1 a 2 minutos.
- Solo debe haber UNA instancia del worker.
- Si el worker deja de latir 2 minutos, un panel de Streamlit abierto retoma los ciclos.
- Para dinero real, un hosting de pago que no se duerma es más seguro que este esquema.
