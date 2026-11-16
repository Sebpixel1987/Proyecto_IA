# Plataforma de Optimización Logística de Última Milla — Emporio Alemán

Sistema web de gestión de despachos y optimización de rutas de Última Milla desarrollado para **Emporio Alemán S.A.** (Gran Concepción, Chile) en colaboración con el **Laboratorio IAnts de la Universidad San Sebastián (USS)**.

El sistema modela la red de distribución como un grafo urbano y resuelve el Problema de Ruteo de Vehículos con Capacidad (CVRP) mediante un ensamble de **Red Neuronal de Grafos (GNN)** + **Optimización por Colonia de Hormigas (ACO)**, integrando visualización geoespacial real y flujos operativos diferenciados por rol[cite: 3, 57].

---

## Arquitectura y Stack Tecnológico

* **Backend:** Python 3, Django 6.x
* **Base de Datos:** PostgreSQL (`emporio_db`)[cite: 76]
* **Motor de Optimización (IA):** Ensamble GNN + ACO ($\alpha=1.0$, $\beta=3.0$, $\rho=0.5$, 12 hormigas, 50 iteraciones)[cite: 79]
* **Geoespacial y Mapas:** `folium`, Leaflet.js, tiles de *Esri World Street Map* y trazado vial real con **OSRM**[cite: 74]
* **Frontend y Reportes:** HTML5, Bootstrap 5, FontAwesome 6, vistas de impresión/PDF nativas (`@media print`)
* **Carga Masiva:** `openpyxl` (`.xlsx`) y módulo estándar `csv`

---

## Reglas de Negocio y Parámetros Operativos

* **Punto de Origen y Retorno:** Planta Emporio Alemán en Chiguayante (`lat: -36.9158`, `lon: -73.0239`)[cite: 5, 79].
* **Cobertura y Zonificación (Gran Concepción):**
  * *Sector Talcahuano – Hualpén:* Martes, Jueves y Sábado (`M-J-S`)[cite: 5].
  * *Sector Concepción Centro – Chiguayante:* Lunes a Sábado[cite: 5].
  * *Eje San Pedro de la Paz – Coronel – Lota:* Lunes, Miércoles y Viernes (`L-M-V`)[cite: 5].
  * *Sector Penco – Lirquén:* Martes y Viernes[cite: 5].
* **Restricciones de Flota (FOTON TM-3):**
  * Capacidad máxima estricta de **1.600 kg** por camión[cite: 5, 78].
  * Máximo de **30 paradas** por ruta asignada[cite: 5, 79].
* **KPIs Operativos:**
  * **Fill Rate:** Meta objetivo $\ge 98\%$[cite: 6].
  * **Lead Time:** Meta objetivo $98\% - 100\%$ (cero pedidos rezagados)[cite: 6].

---

## Funcionalidades Implementadas

1. **Gestión Multi-Rol (`/`, `/login/`, `/dashboard/`):**
   * **Cliente (`/registro-cliente/`, `/panel-cliente/`):** Autoregistro con selección de coordenadas en mapa interactivo (Esri), creación de pedidos desde catálogo con stock en tiempo real, ventanas horarias y restricciones de entrega.
   * **Administrador (`/panel-admin/`):** Gestión de catálogo y stock de productos, supervisión de pedidos en preventa, ejecución del motor GNN + ACO por zona/fecha, monitoreo de KPIs (*Fill Rate* y *Lead Time*), mapa OSRM multi-ruta (`/mapa/`) e historial de despachos (`/historial/`).
   * **Conductor (`/panel-conductor/`):** Visualización exclusiva de su camión asignado, secuencia ordenada de paradas, restricciones del cliente y confirmación de entregas en terreno.
2. **Hoja de Ruta Imprimible / PDF (`/ruta/imprimir/<camion_id>/`):**
   * Documento limpio optimizado para impresión y exportación a PDF con resumen de carga, croquis de ruta trazada con OSRM, detalle de picking por parada y firmas de control[cite: 5].
3. **Carga Masiva Estandarizada (`/carga-masiva/`):**
   * Importación de clientes, ubicaciones y pedidos desde archivos Excel (`.xlsx`) o `.csv` con validación transaccional por fila y descarga de plantilla oficial (`/carga-masiva/plantilla/`).

---

## Instalación y Puesta en Marcha (Linux / WSL)

### 1. Clonar repositorio y activar entorno virtual
```bash
git clone <URL_DEL_REPOSITORIO>
cd Proyecto_IA
python3 -m venv venv
source venv/bin/activate

2. Instalar dependencias
Bash
pip install django psycopg2-binary folium requests openpyxl

3. Configurar Base de Datos PostgreSQL
Asegúrate de tener PostgreSQL activo y creada la base de datos configurada en sistema_reclutamiento/settings.py (emporio_db)[cite: 76]:

Bash
sudo service postgresql start
python manage.py makemigrations
python manage.py migrate

4. Poblar datos iniciales (Opcional)
Bash
python manage.py seed_data
python manage.py createsuperuser

5. Ejecutar servidor de desarrollo
Bash
python manage.py runserver
Accede en el navegador a: http://127.0.0.1:8000/