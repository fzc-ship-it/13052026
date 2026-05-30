# BOE Auction Scraper - Profesional

Sistema robusto de scraping para subastas de inmuebles del BOE con motor diferencial, sistema antibloqueo avanzado y gestión relacional de datos.

## Requisitos
- Python 3.12+
- Dependencias listadas en `requirements.txt`
- Playwright Chromium

## Instalación
```bash
pip install -r requirements.txt
playwright install chromium
```

## Uso Diario (Incremental)
El sistema está diseñado para ser extremadamente eficiente. No es necesario realizar un barrido completo todos los días.

### 1. Sincronización Rápida
Ejecuta el scraper sin parámetros adicionales para detectar nuevas subastas y actualizar el estado de las locales (por ejemplo, de "Próxima apertura" a "Celebrándose").
```bash
python main.py
```
Este comando:
- Escanea IDs actuales en el portal (rápido).
- Detecta subastas que han concluido y las clasifica (revisa pujas automáticamente).
- Solo realiza el "Scraping Profundo" (lento) para los IDs nuevos o incompletos.

### 2. Sincronización Histórica
Si deseas buscar subastas que han finalizado recientemente en el portal y no estaban en tu base de datos local:
```bash
python main.py --days 7
```

## Consultas y Reportes
Utiliza `query_tool.py` para filtrar la base de datos y generar archivos Excel.

### Ver "Cesión de remate" (Sin pujas)
```bash
python query_tool.py --status "remate" --export excel
```

### Filtrado por Provincia y Precio
```bash
python query_tool.py --provincia Madrid --max-price 200000 --export excel
```

## Arquitectura
- **`main.py`**: Motor de sincronización diferencial.
- **`src/scraper.py`**: Lógica de navegación y extracción verificada.
- **`src/stealth_manager.py`**: Evasión de bloqueos y simulación humana.
- **`src/database.py`**: Persistencia relacional (Subastas -> Lotes).
- **`src/query_engine.py`**: Motor de búsqueda y exportación.

## Docker
Puedes ejecutar todo el entorno de forma aislada:
```bash
docker build -t boe-scraper .
docker run -v $(pwd)/data:/app/data boe-scraper
```
