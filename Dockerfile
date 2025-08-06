# Dockerfile

# 1. Usa una imagen oficial de Python como base
FROM python:3.11-slim

# 2. Establece el directorio de trabajo
WORKDIR /app

# 3. Copia SOLO el archivo de requerimientos primero
# Esto aprovecha el caché de Docker. Si requirements.txt no cambia, no se reinstala todo.
COPY requirements.txt .

# 4. Instala las librerías de Python (esto instalará el COMANDO `playwright`)
RUN pip install --no-cache-dir -r requirements.txt

# 5. AHORA, con el comando ya disponible, instala las dependencias del sistema
RUN playwright install-deps firefox

# 6. Y después, instala el NAVEGADOR Firefox
RUN playwright install firefox

# 7. Copia el resto de los archivos de tu aplicación
COPY . .

# 8. El comando para iniciar tu aplicación
CMD ["streamlit", "run", "Main.py", "--server.port", "10000", "--server.address", "0.0.0.0"]