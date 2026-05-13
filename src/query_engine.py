import pandas as pd
import json
from src.database import DatabaseManager

class QueryEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def search_auctions(self, province=None, min_price=None, max_price=None, cp=None):
        """Perform search with structured filters."""
        filters = {
            "provincia": province,
            "min_price": min_price,
            "max_price": max_price,
            "cp": cp
        }
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}

        results = self.db.query_auctions(filters)
        return results

    def get_as_dataframe(self, results):
        """Converts results to a pandas DataFrame."""
        if not results:
            return pd.DataFrame()
        return pd.DataFrame(results)

    def export_to_excel(self, results, filename="filtered_auctions.xlsx"):
        """Exports results to an Excel file."""
        df = self.get_as_dataframe(results)
        if not df.empty:
            # We don't want to include the full raw_data in the Excel usually,
            # or maybe we do? Let's drop it for the summary but keep the rest.
            if 'raw_data' in df.columns:
                df = df.drop(columns=['raw_data'])
            df.to_excel(filename, index=False)
            return True
        return False

    def export_to_json(self, results, filename="filtered_auctions.json"):
        """Exports results to a JSON file."""
        if not results:
            return False
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        return True

if __name__ == "__main__":
    # Quick test of the QueryEngine
    db = DatabaseManager(db_name="test_boe.db")
    engine = QueryEngine(db)

    # Get all
    all_auctions = engine.search_auctions()
    print(f"Found {len(all_auctions)} auctions in total.")

    # Filter by price if any
    expensive = engine.search_auctions(min_price=100000)
    print(f"Found {len(expensive)} auctions over 100k.")

    # Export
    engine.export_to_json(all_auctions, "test_export.json")
    print("Exported to test_export.json")
