# BOE Auction Scraper v4 (Optimized)

Este sistema avanzado permite automatizar la extracción, sincronización y consulta de subastas de inmuebles del portal oficial del BOE. Está diseñado para ser rápido, robusto y servir como motor de datos para aplicaciones frontend.

## Características Principales
- **Ciclo de Sincronización Diferencial (10 min)**: No descarga todo de cero. Escanea estados, detecta transiciones (ej: de Próxima a Activa) y solo extrae el detalle de subastas nuevas.
- **Módulo Antibloqueo**: Simulación humana avanzada con Playwright, rotación de User-Agents y gestión de cabeceras realistas.
- **Estructura Relacional**: Base de datos SQLite que separa Subastas de Lotes individuales, permitiendo capturar datos económicos específicos por cada bien.
- **Extracción Exhaustiva**: Captura fechas, tipologías (Vivienda, Garaje, etc.), datos de la autoridad gestora y detalles de catastro.
- **Filtrado Avanzado**: Motor de búsqueda integrado para filtrar por provincia, precio, CP y tipología.

## Instalación Local

1. **Requisitos**: Python 3.12+ instalado.
2. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Instalar navegadores de Playwright**:
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

## Guía de Uso

### 1. Ejecutar la Sincronización Diaria
Este comando realiza el escaneo rápido y descarga solo las nuevas subastas:
```bash
python main.py
```

### 2. Consultar y Filtrar Datos
Utiliza `query_tool.py` para trabajar con los datos almacenados en `boe_auctions.db`.

**Ejemplos:**
- **Ver subastas en una provincia**:
  ```bash
  python query_tool.py --provincia Madrid
  ```
- **Filtrar por precio y exportar a Excel**:
  ```bash
  python query_tool.py --min-price 100000 --export excel --output mi_reporte
  ```
  *Nota: El Excel generado es plano, donde cada fila representa un lote/bien individual con la información de su subasta asociada.*

## Estructura de Datos (Excel/DB)
- **estado_proceso**: "Próxima apertura", "Celebrándose", "Concluida" o "Finalizada".
- **tipologia**: Clasificación extraída (ej: Vivienda, Local comercial).
- **valor_subasta / tasacion**: Valores económicos normalizados a número para cálculos.

## Uso con Docker
```bash
docker build -t boe-scraper .
docker run -v $(pwd):/app boe-scraper python main.py
```
