Para dejar tu nuevo equipo exactamente igual al anterior y retomar el proyecto del Emporio Alemán, Jarvis, debes seguir esta secuencia. Se divide en instalar las herramientas base en Windows, configurar tu entorno Linux (Debian) y finalmente descargar y levantar tu código.

1. Descargas base en Windows

Visual Studio Code: Descarga e instala el editor de código.

Git for Windows: Descárgalo para poder traer tu código desde GitHub.

Extensión WSL: Abre VS Code, ve a Extensiones (Ctrl + Shift + X) e instala la extensión oficial "WSL" de Microsoft.

2. Activar WSL y Debian
Abre una terminal normal de PowerShell en Windows como Administrador y ejecuta este comando para instalar el subsistema de Linux con Debian:

PowerShell
wsl --install -d Debian
Te pedirá reiniciar el equipo. Al volver, se abrirá una ventana para que crees un usuario y contraseña de Linux.

3. Instalar dependencias en Debian
Abre VS Code, conéctate a WSL (con el botón inferior izquierdo o desde la paleta de comandos) y abre una nueva terminal de Linux. Ejecuta:

Bash
sudo apt update
sudo apt install postgresql postgresql-contrib python3-venv python3-dev libpq-dev build-essential git
4. Clonar tu código desde GitHub
En esa misma terminal de Debian, trae el código que guardaste en la sesión anterior:

Bash
git clone TU_URL_DE_GITHUB_AQUI
cd sistema_reclutamiento
5. Recrear la base de datos PostgreSQL
Debemos armar la base de datos del Emporio desde cero en este nuevo equipo:

Bash
sudo -u postgres psql
Dentro de la consola SQL:

SQL
CREATE DATABASE emporio_db;
CREATE USER ragnarok_admin WITH PASSWORD 'ragnarok2026';
ALTER ROLE ragnarok_admin SET client_encoding TO 'utf8';
ALTER ROLE ragnarok_admin SET default_transaction_isolation TO 'read committed';
ALTER ROLE ragnarok_admin SET timezone TO 'America/Santiago';
GRANT ALL PRIVILEGES ON DATABASE emporio_db TO ragnarok_admin;
\c emporio_db
GRANT ALL ON SCHEMA public TO ragnarok_admin;
\q
6. Levantar el entorno virtual de Python
Finalmente, crea el entorno virtual, instala Django y conecta todo:

Bash
python3 -m venv venv
source venv/bin/activate
pip install django psycopg2
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
