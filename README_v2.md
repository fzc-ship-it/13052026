# BOE Auction Scraper v2

Este sistema permite automatizar la extracción, filtrado y consulta de subastas de inmuebles del portal oficial del BOE.

## Características Principales
- **Módulo Antibloqueo**: Rotación de User-Agents, cabeceras realistas y simulación de comportamiento humano mediante Playwright.
- **Scraping Eficiente**: Carga incremental y filtrado por fechas para ejecución diaria rápida.
- **Filtrado Avanzado**: Base de datos SQLite integrada para realizar consultas por precio, provincia y código postal.
- **Detección de Pujas**: Identifica automáticamente subastas finalizadas sin pujas.

## Instalación Local

1. **Requisitos**: Python 3.12+ instalado.
2. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Instalar navegadores de Playwright**:
   ```bash
   playwright install chromium
   ```

## Guía de Uso

### 1. Ejecutar el Scraper (Obtención de Datos)
Para descargar las subastas de los últimos X días (por defecto 1 día):
```bash
python main.py --days 1
```
*Nota: La primera ejecución puede tardar más si se desea obtener un historial largo.*

### 2. Consultar y Filtrar Datos
Utiliza la herramienta `query_tool.py` para realizar búsquedas rápidas en los datos guardados.

**Ejemplos:**
- **Ver todas las subastas en Madrid**:
  ```bash
  python query_tool.py --provincia Madrid
  ```
- **Filtrar por precio y exportar a Excel**:
  ```bash
  python query_tool.py --min-price 50000 --max-price 200000 --export excel --output mi_busqueda
  ```
- **Ver solo subastas sin pujas**:
  ```bash
  python query_tool.py --sin-pujas
  ```

## Uso con Docker
Si prefieres usar Docker para evitar instalar dependencias locales:
```bash
docker build -t boe-scraper .
docker run -v $(pwd):/app boe-scraper python main.py --days 1
```

## Estructura del Proyecto
- `src/scraper.py`: Lógica principal de navegación y extracción.
- `src/stealth_manager.py`: Configuración antibloqueo.
- `src/database.py`: Gestión de persistencia en SQLite.
- `src/query_engine.py`: Motor de búsqueda y exportación.
- `main.py`: Punto de entrada para el scraping diario.
- `query_tool.py`: Herramienta CLI para el usuario.
