import argparse
import json
from src.database import DatabaseManager
from src.query_engine import QueryEngine

def main():
    parser = argparse.ArgumentParser(description="Herramienta de consulta de subastas BOE")
    parser.add_argument("--db", default="boe_auctions.db", help="Ruta a la base de datos SQLite")
    parser.add_argument("--provincia", help="Filtrar por nombre de provincia")
    parser.add_argument("--status", help="Filtrar por estado (ej: 'Cesión de remate', 'Celebrándose')")
    parser.add_argument("--min-price", type=float, help="Precio mínimo")
    parser.add_argument("--max-price", type=float, help="Precio máximo")
    parser.add_argument("--cp", help="Código postal exacto")
    parser.add_argument("--export", choices=["excel", "json"], help="Exportar resultados")
    parser.add_argument("--output", default="resultados_busqueda", help="Nombre del archivo de salida (sin extensión)")

    args = parser.parse_args()

    db = DatabaseManager(db_name=args.db)
    engine = QueryEngine(db)

    filters = {}
    if args.provincia: filters["provincia"] = args.provincia
    if args.status: filters["estado_proceso"] = args.status
    if args.min_price: filters["min_price"] = args.min_price
    if args.max_price: filters["max_price"] = args.max_price
    if args.cp: filters["cp"] = args.cp

    results = engine.search_auctions(**filters)

    print(f"\n--- Resultados de la búsqueda ({len(results)} encontrados) ---")
    for r in results[:10]: # Show first 10
        # Adapt keys for preview display
        id_val = r.get('identificador', r.get('auction_id', 'N/A'))
        prov = r.get('bien_provincia', 'N/A')
        price = r.get('valor_subasta', 'N/A')
        print(f"ID: {id_val} | Provincia: {prov} | Precio: {price}€")

    if len(results) > 10:
        print(f"... y {len(results) - 10} más.")

    if not args.export and results:
        print(f"\n[!] Sugerencia: Usa '--export excel' para generar un archivo Excel con todos los datos.")

    if args.export == "excel":
        filename = f"{args.output}.xlsx"
        if engine.export_to_excel(results, filename):
            print(f"\n[+] Exportado exitosamente a {filename}")
    elif args.export == "json":
        filename = f"{args.output}.json"
        if engine.export_to_json(results, filename):
            print(f"\n[+] Exportado exitosamente a {filename}")

if __name__ == "__main__":
    main()
