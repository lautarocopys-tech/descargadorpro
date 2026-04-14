# El Descargador Pro — Web Version

Aplicación web para descargar videos y música de YouTube, Instagram, TikTok y +1000 sitios.

## Estructura

```
web/
├── frontend/          # Interfaz web (HTML, CSS, JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── server.py          # API Backend (FastAPI + yt-dlp)
├── requirements.txt   # Dependencias de Python
└── README.md
```

## Ejecución local

```bash
cd web
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Abrí tu navegador en: `http://localhost:8000`

## Deploy en Render

1. Subí la carpeta `web/` a un repo de GitHub
2. En Render, creá un nuevo **Web Service**
3. Configurá:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3
4. Render te dará una URL pública como: `https://tu-app.onrender.com`

## Variables de entorno opcionales

| Variable      | Default        | Descripción                                 |
|---------------|----------------|---------------------------------------------|
| `DOWNLOAD_DIR`| `/tmp/downloads` | Carpeta temporal para archivos descargados |
| `FILE_TTL`    | `600`          | Segundos antes de borrar archivos temporales |
