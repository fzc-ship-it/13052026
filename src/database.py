import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_name="boe_auctions.db"):
        self.db_name = db_name
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auctions (
                    identificador TEXT PRIMARY KEY,
                    url TEXT,
                    provincia TEXT,
                    tipo_de_bien TEXT,
                    estado_subasta TEXT,
                    precio_salida REAL,
                    codigo_postal TEXT,
                    sin_pujas INTEGER DEFAULT 0,
                    raw_data TEXT,
                    last_updated TIMESTAMP
                )
            """)
            conn.commit()

    def auction_exists(self, identificador):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM auctions WHERE identificador = ?", (identificador,))
            return cursor.fetchone() is not None

    def save_auction(self, auction_data):
        identificador = auction_data.get("identificador")
        if not identificador:
            return

        provincia = auction_data.get("provincia", auction_data.get("provincia_search", ""))
        tipo = auction_data.get("tipo_de_bien", "")
        estado = auction_data.get("estado_subasta", "")
        cp = auction_data.get("código_postal", "")
        sin_pujas = 1 if auction_data.get("sin_pujas") else 0

        precio_salida = auction_data.get("valor_subasta", "0")
        try:
            # Cleanup currency
            precio_salida = float(precio_salida.replace("€", "").replace(".", "").replace(",", ".").strip())
        except ValueError:
            precio_salida = 0.0

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO auctions
                (identificador, url, provincia, tipo_de_bien, estado_subasta, precio_salida, codigo_postal, sin_pujas, raw_data, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                identificador,
                auction_data.get("url"),
                provincia,
                tipo,
                estado,
                precio_salida,
                cp,
                sin_pujas,
                json.dumps(auction_data),
                datetime.now().isoformat()
            ))
            conn.commit()

    def query_auctions(self, filters=None):
        query = "SELECT * FROM auctions WHERE 1=1"
        params = []

        if filters:
            if filters.get("provincia"):
                query += " AND provincia LIKE ?"
                params.append(f"%{filters['provincia']}%")
            if filters.get("min_price"):
                query += " AND precio_salida >= ?"
                params.append(filters["min_price"])
            if filters.get("max_price"):
                query += " AND precio_salida <= ?"
                params.append(filters["max_price"])
            if filters.get("cp"):
                query += " AND codigo_postal = ?"
                params.append(filters["cp"])
            if "sin_pujas" in filters:
                query += " AND sin_pujas = ?"
                params.append(1 if filters["sin_pujas"] else 0)

        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
