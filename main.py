import os
import shutil
import boto3
from botocore.client import Config
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno
load_dotenv()

# --- CONFIGURACIÓN ---
# Nombres de los buckets de Minio
BUCKETS = ["bots", "n8n", "portafolio", "yodumanager-prod"]

# Directorio local temporal para descargas
LOCAL_BACKUP_DIR = Path("backups")

# ID de la carpeta principal en Google Drive
DRIVE_PARENT_ID = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID")

# Archivos de credenciales OAuth2
CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CREDENTIALS") # El JSON descargado de Google Console (Desktop App)
TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN", "token.json") # Se generará automáticamente la primera vez

# Configuración Minio S3
MINIO_URL = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET = os.getenv("MINIO_SECRET_KEY")

# Alcance de permisos para Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Inicializa y retorna el servicio de Google Drive usando OAuth2."""
    creds = None
    # El archivo token.json almacena los tokens de acceso y refresco del usuario
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # Si no hay credenciales válidas disponibles, pedir al usuario que inicie sesión.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE or not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"No se encontró el archivo de credenciales OAuth en: {CREDENTIALS_FILE}")
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # Forzamos puerto 8080 para mayor consistencia
            creds = flow.run_local_server(port=8080, bind_addr='localhost')
        
        # Guardar las credenciales para la próxima ejecución
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def get_s3_client():
    """Inicializa y retorna el cliente de Minio S3."""
    # Asegurar que el URL no termine en slash si se usa con path style a veces ayuda
    endpoint = MINIO_URL.rstrip('/') if MINIO_URL else None
    
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ACCESS,
        aws_secret_access_key=MINIO_SECRET,
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'}
        ),
        region_name='us-east-1'
    )

def get_or_create_drive_folder(service, name, parent_id):
    """Busca una carpeta por nombre en Drive, si no existe la crea."""
    query = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(
        q=query, 
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']
    
    # Si no existe, crearla
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(
        body=file_metadata, 
        fields='id',
        supportsAllDrives=True
    ).execute()
    print(f"Directorio creado en Drive: {name}")
    return folder.get('id')

def get_drive_files_in_folder(service, folder_id):
    """Obtiene una lista de nombres de archivos en una carpeta específica de Drive."""
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query, 
        fields="files(name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get('files', [])
    return [f['name'] for f in files]

def download_s3_bucket(s3, bucket_name):
    """Descarga todos los archivos de un bucket a la carpeta local."""
    bucket_path = LOCAL_BACKUP_DIR / bucket_name
    bucket_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n--- Procesando Bucket: {bucket_name} ---")
    
    # Listar objetos en el bucket
    objects = s3.list_objects_v2(Bucket=bucket_name)
    downloaded_files = []

    if 'Contents' in objects:
        for obj in objects['Contents']:
            file_key = obj['Key']
            local_file_path = bucket_path / file_key
            
            # Asegurar que existan subcarpetas si el key tiene "/"
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"Descargando {file_key}...")
            # Usar get_object en lugar de download_file para evitar HeadObject automático
            response = s3.get_object(Bucket=bucket_name, Key=file_key)
            with open(local_file_path, 'wb') as f:
                f.write(response['Body'].read())
            
            downloaded_files.append((file_key, local_file_path))
    else:
        print(f"El bucket {bucket_name} está vacío.")
        
    return downloaded_files

def main():
    # Inicializar servicios
    s3 = get_s3_client()
    try:
        drive = get_drive_service()
    except Exception as e:
        print(f"Error de autenticación con Google Drive: {e}")
        return

    # Asegurar directorio local de backups
    LOCAL_BACKUP_DIR.mkdir(exist_ok=True)

    for bucket_name in BUCKETS:
        # 1. Descargar archivos del bucket
        files_to_sync = download_s3_bucket(s3, bucket_name)
        
        if not files_to_sync:
            continue

        # 2. Obtener o crear carpeta del bucket en Drive
        drive_bucket_folder_id = get_or_create_drive_folder(drive, bucket_name, DRIVE_PARENT_ID)
        
        # 3. Subir archivos faltantes manejando subcarpetas
        for file_key, local_path in files_to_sync:
            # Separar la ruta de S3 en partes
            path_parts = file_key.split('/')
            file_name = path_parts[-1]
            sub_folders = path_parts[:-1]
            
            # Navegar o crear subcarpetas en Drive
            current_parent_id = drive_bucket_folder_id
            for folder_name in sub_folders:
                current_parent_id = get_or_create_drive_folder(drive, folder_name, current_parent_id)
            
            # Verificar si el archivo ya está en esa subcarpeta específica
            existing_files = get_drive_files_in_folder(drive, current_parent_id)
            
            if file_name not in existing_files:
                print(f"Subiendo a Drive: {file_key}")
                
                file_metadata = {
                    'name': file_name,
                    'parents': [current_parent_id]
                }
                media = MediaFileUpload(str(local_path), resumable=True)
                drive.files().create(
                    body=file_metadata, 
                    media_body=media, 
                    fields='id',
                    supportsAllDrives=True
                ).execute()
            else:
                print(f"Saltando {file_key} (ya existe en Drive)")

    print("\n¡Proceso de respaldo completado!")

    # Limpieza: Borrar los archivos locales descargados para no ocupar espacio en el VPS
    if LOCAL_BACKUP_DIR.exists():
        print(f"Limpiando archivos temporales en {LOCAL_BACKUP_DIR}...")
        shutil.rmtree(LOCAL_BACKUP_DIR)
        print("Archivos temporales eliminados.")

if __name__ == "__main__":
    main()
