Sistema de Logística y Rutas - Emporio Alemán 🚚

Este proyecto es una aplicación web desarrollada en Django y PostgreSQL para gestionar clientes, pedidos y optimizar rutas de entrega para el Emporio Alemán.

Requisitos Previos (Windows)

Antes de comenzar, asegúrate de tener instalado en tu equipo Windows:

Visual Studio Code

Git for Windows

Extensión WSL instalada en VS Code.

Guía de Instalación Paso a Paso

1. Activar Entorno Linux (WSL)

Abre PowerShell como Administrador en Windows y ejecuta:

wsl --install -d Debian


(Reinicia tu equipo si es necesario. Al abrir de nuevo, configura tu usuario y contraseña de Linux).

2. Instalar Dependencias del Sistema

Abre VS Code, conéctate a WSL (Debian) y abre una nueva terminal de Linux. Ejecuta los siguientes comandos para actualizar el sistema e instalar Python, PostgreSQL y herramientas necesarias:

sudo apt update
sudo apt install postgresql postgresql-contrib python3-venv python3-dev libpq-dev build-essential git


3. Clonar el Repositorio

Descarga el código del proyecto desde GitHub y entra a la carpeta:

git clone <TU_URL_DE_GITHUB_AQUI>
cd sistema_reclutamiento


(Nota: La carpeta raíz mantiene el nombre heredado de la base inicial).

4. Configurar la Base de Datos (PostgreSQL)

Ingresa a la consola de PostgreSQL:

sudo -u postgres psql


Dentro de la consola SQL, ejecuta línea por línea para crear la base de datos y otorgar permisos:

CREATE DATABASE emporio_db;
CREATE USER ragnarok_admin WITH PASSWORD 'ragnarok2026';
ALTER ROLE ragnarok_admin SET client_encoding TO 'utf8';
ALTER ROLE ragnarok_admin SET default_transaction_isolation TO 'read committed';
ALTER ROLE ragnarok_admin SET timezone TO 'America/Santiago';
GRANT ALL PRIVILEGES ON DATABASE emporio_db TO ragnarok_admin;
\c emporio_db
GRANT ALL ON SCHEMA public TO ragnarok_admin;
\q


5. Entorno Virtual e Instalación de Librerías

Crea y activa el entorno virtual de Python. Luego instala Django y el conector de PostgreSQL:

python3 -m venv venv
source venv/bin/activate
pip install django psycopg2


(Nota: Si más adelante agregamos más librerías, asegúrate de usar pip install -r requirements.txt si existe).

6. Migraciones y Usuario Administrador

Conecta el código a la base de datos creando las tablas y un usuario para acceder al panel web:

python3 manage.py migrate
python3 manage.py createsuperuser


(Sigue las instrucciones en pantalla para definir tu usuario, email y contraseña).

7. Levantar el Servidor

Finalmente, enciende el servidor local:

python3 manage.py runserver


Abre tu navegador y entra a http://localhost:8000/admin para comenzar a gestionar Clientes y Pedidos.

Nota para el equipo: Recuerden siempre activar el entorno virtual (source venv/bin/activate) cada vez que abran una nueva terminal para trabajar en el proyecto.
