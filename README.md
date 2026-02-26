# Backups S3 (Minio) a Google Drive 🚀

Este script automatiza el proceso de respaldar archivos desde buckets de **Minio (S3)** hacia una carpeta específica en **Google Drive**, manteniendo la estructura de directorios y evitando duplicados.

## ✨ Características

- **Sincronización Inteligente**: Solo sube archivos que no existen en Google Drive (comparación por nombre).
- **Estructura de Carpetas**: Replica las subcarpetas de S3 automáticamente en Drive.
- **Autolimpieza**: Borra los archivos locales descargados después de subirlos para ahorrar espacio en disco (ideal para VPS).
- **OAuth2**: Utiliza autenticación de usuario personal para evitar límites de cuota de cuentas de servicio.

## 🛠️ Requisitos previos

1.  **Python 3.x** instalado.
2.  **Minio/S3**: Credenciales de acceso y URL del endpoint.
3.  **Google Cloud Console**:
    - Crear un proyecto.
    - Habilitar la **Google Drive API**.
    - Crear credenciales de tipo **ID de cliente de OAuth 2.0** (Tipo: App de escritorio).
    - Descargar el JSON y renombrarlo como `credentials.json`.
    - **Importante**: Agregar tu correo en la sección de "Test Users" de la pantalla de consentimiento.

## 🚀 Instalación

1.  Clona este repositorio o copia los archivos.
2.  Crea un entorno virtual e instala las dependencias:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install boto3 google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv
    ```
3.  Configura el archivo `.env` (ver sección de Configuración).

## ⚙️ Configuración (.env)

Crea un archivo `.env` en la raíz del proyecto con el siguiente contenido:

```env
# Minio / S3
MINIO_ENDPOINT=http://tu-ip-o-dominio:9000
MINIO_ACCESS_KEY=tu_usuario
MINIO_SECRET_KEY=tu_password

# Google Drive
GOOGLE_DRIVE_PARENT_FOLDER_ID=ID_DE_LA_CARPETA_DESTINO
GOOGLE_OAUTH_CREDENTIALS=credentials.json
```

*Nota: Para obtener el `ID_DE_LA_CARPETA_DESTINO`, abre la carpeta en tu navegador y copia la última parte de la URL.*

## 🏃 Uso

Para ejecutar el script:
```bash
python main.py
```

**Primera ejecución**: Se abrirá una ventana en tu navegador para autorizar el acceso a tu Google Drive. Esto generará un archivo `token.json` que permitirá ejecuciones automáticas futuras (como en un Cron).

## 📅 Automatización (Cron)

Para ejecutarlo automáticamente en un VPS cada día a las 2 AM:

1.  Abre el crontab: `crontab -e`
2.  Agrega la siguiente línea (ajusta las rutas):
    ```cron
    0 2 * * * /ruta/al/proyecto/.venv/bin/python /ruta/al/proyecto/main.py >> /ruta/al/proyecto/backups.log 2>&1
    ```

## 📝 Notas
- El script ignora archivos en la papelera de Google Drive.
- Si el archivo `token.json` existe, el script no pedirá interacción humana, lo que lo hace perfecto para servidores.
