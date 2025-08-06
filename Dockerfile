# Dockerfile

# Usa una imagen oficial de Python como base
FROM python:3.11-slim

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala las dependencias del sistema que Firefox necesita para correr en Linux
# Esto se ejecuta como administrador (ROOT) de forma segura durante la construcción
RUN playwright install-deps firefox

# Copia el archivo de requerimientos e instálalos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala el NAVEGADOR Firefox en sí
# Esto se ejecuta después de que las dependencias del sistema están listas
RUN playwright install firefox

# Copia el resto de los archivos de tu aplicación al contenedor
COPY . .

# El comando para iniciar tu aplicación
# Render expone el puerto 10000 para los Web Services con Docker
CMD ["streamlit", "run", "app.py", "--server.port", "10000", "--server.address", "0.0.0.0"]