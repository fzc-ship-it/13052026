import pandas as pd
import json
from src.database import DatabaseManager

class QueryEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def search_auctions(self, provincia=None, min_price=None, max_price=None, cp=None):
        """Perform search with structured filters on the flat lot results."""
        filters = {
            "provincia": provincia,
            "min_price": min_price,
            "max_price": max_price,
            "cp": cp
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        results = self.db.get_flat_results(filters)
        return results

    def export_to_excel(self, results, filename="subastas_reporte.xlsx"):
        """Exports results to a flat Excel file where each row is a Lot."""
        if not results:
            return False

        df = pd.DataFrame(results)

        # Reorder columns to have Auction metadata first
        cols = list(df.columns)
        metadata_cols = [
            'identificador', 'tipo_subasta', 'fecha_inicio', 'fecha_conclusion',
            'autoridad_gestora_codigo', 'autoridad_gestora_telefono', 'autoridad_gestora_email',
            'estado_proceso', 'url'
        ]
        lot_cols = [c for c in cols if c not in metadata_cols and c != 'raw_data' and c != 'last_updated']

        # Filter existing columns
        metadata_cols = [c for c in metadata_cols if c in cols]
        lot_cols = [c for c in lot_cols if c in cols]

        final_cols = metadata_cols + lot_cols
        df = df[final_cols]

        df.to_excel(filename, index=False)
        return True

    def export_to_json(self, results, filename="subastas_reporte.json"):
        if not results:
            return False
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        return True
