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
            # Auctions table (Parent)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auctions (
                    identificador TEXT PRIMARY KEY,
                    url TEXT,
                    tipo_subasta TEXT,
                    fecha_inicio TEXT,
                    fecha_conclusion TEXT,
                    tiene_lotes INTEGER,
                    autoridad_gestora_codigo TEXT,
                    autoridad_gestora_telefono TEXT,
                    autoridad_gestora_email TEXT,
                    estado_proceso TEXT,
                    raw_data TEXT,
                    last_updated TIMESTAMP
                )
            """)

            # Lots/Property table (Child)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    auction_id TEXT,
                    lote_numero INTEGER,
                    cantidad_reclamada REAL,
                    valor_subasta REAL,
                    tasacion REAL,
                    puja_minima REAL,
                    importe_deposito REAL,
                    tramos_entre_pujas TEXT,
                    bien_tipo TEXT,
                    bien_descripcion TEXT,
                    bien_direccion TEXT,
                    bien_referencia_catastral TEXT,
                    bien_idufir TEXT,
                    bien_codigo_postal TEXT,
                    bien_localidad TEXT,
                    bien_provincia TEXT,
                    bien_vivienda_habitual TEXT,
                    bien_situacion_posesoria TEXT,
                    bien_visitable TEXT,
                    bien_cargas TEXT,
                    FOREIGN KEY (auction_id) REFERENCES auctions (identificador) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def auction_exists(self, identificador):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM auctions WHERE identificador = ?", (identificador,))
            return cursor.fetchone() is not None

    def _parse_price(self, value):
        if not value or not isinstance(value, str):
            return 0.0
        try:
            # Handle formats like "123.456,78 €" or just "123456.78"
            clean = value.replace("€", "").replace(".", "").replace(",", ".").strip()
            return float(clean)
        except (ValueError, AttributeError):
            return 0.0

    def save_full_auction(self, auction_data, status_code):
        """Saves an auction and all its associated lots."""
        identificador = auction_data.get("identificador")
        if not identificador:
            return

        tiene_lotes = 1 if auction_data.get("lotes") and auction_data.get("lotes") != "Sin lotes" else 0

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            # 1. Insert/Update Parent Auction
            cursor.execute("""
                INSERT OR REPLACE INTO auctions
                (identificador, url, tipo_subasta, fecha_inicio, fecha_conclusion, tiene_lotes,
                 autoridad_gestora_codigo, autoridad_gestora_telefono, autoridad_gestora_email,
                 estado_proceso, raw_data, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                identificador,
                auction_data.get("url"),
                auction_data.get("tipo_de_subasta"),
                auction_data.get("fecha_de_inicio"),
                auction_data.get("fecha_de_conclusión"),
                tiene_lotes,
                auction_data.get("código"),
                auction_data.get("teléfono"),
                auction_data.get("correo_electrónico"),
                status_code,
                json.dumps(auction_data),
                datetime.now().isoformat()
            ))

            # 2. Clear old lots for this auction to avoid duplicates on update
            cursor.execute("DELETE FROM lots WHERE auction_id = ?", (identificador,))

            # 3. Insert Lots
            lots_list = auction_data.get("lots_data", [])
            if not lots_list:
                # Handle single lot (data is in the main auction object)
                # Map fields from the main object to the lot structure
                cursor.execute("""
                    INSERT INTO lots
                    (auction_id, lote_numero, cantidad_reclamada, valor_subasta, tasacion,
                     puja_minima, importe_deposito, tramos_entre_pujas, bien_tipo, bien_descripcion,
                     bien_direccion, bien_referencia_catastral, bien_idufir, bien_codigo_postal,
                     bien_localidad, bien_provincia, bien_vivienda_habitual, bien_situacion_posesoria,
                     bien_visitable, bien_cargas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    identificador,
                    0, # Single lot indicator
                    self._parse_price(auction_data.get("cantidad_reclamada")),
                    self._parse_price(auction_data.get("valor_subasta")),
                    self._parse_price(auction_data.get("tasación")),
                    self._parse_price(auction_data.get("puja_mínima")),
                    self._parse_price(auction_data.get("importe_del_depósito")),
                    auction_data.get("tramos_entre_pujas"),
                    auction_data.get("bien"),
                    auction_data.get("descripción"),
                    auction_data.get("dirección"),
                    auction_data.get("referencia_catastral"),
                    auction_data.get("idufir"),
                    auction_data.get("código_postal"),
                    auction_data.get("localidad"),
                    auction_data.get("provincia"),
                    auction_data.get("vivienda_habitual"),
                    auction_data.get("situación_posesoria"),
                    auction_data.get("visitable"),
                    auction_data.get("cargas")
                ))
            else:
                # Handle multiple lots
                for lot in lots_list:
                    cursor.execute("""
                        INSERT INTO lots
                        (auction_id, lote_numero, cantidad_reclamada, valor_subasta, tasacion,
                         puja_minima, importe_deposito, tramos_entre_pujas, bien_tipo, bien_descripcion,
                         bien_direccion, bien_referencia_catastral, bien_idufir, bien_codigo_postal,
                         bien_localidad, bien_provincia, bien_vivienda_habitual, bien_situacion_posesoria,
                         bien_visitable, bien_cargas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        identificador,
                        lot.get("lote_numero"),
                        self._parse_price(lot.get("cantidad_reclamada")),
                        self._parse_price(lot.get("valor_subasta_del_lote")),
                        self._parse_price(lot.get("valor_de_tasación_del_lote")),
                        self._parse_price(lot.get("puja_mínima_del_lote")),
                        self._parse_price(lot.get("importe_del_depósito_del_lote")),
                        lot.get("tramos_entre_pujas"),
                        lot.get("bien"),
                        lot.get("descripción"),
                        lot.get("dirección"),
                        lot.get("referencia_catastral"),
                        lot.get("idufir"),
                        lot.get("código_postal"),
                        lot.get("localidad"),
                        lot.get("provincia"),
                        lot.get("vivienda_habitual"),
                        lot.get("situación_posesoria"),
                        lot.get("visitable"),
                        lot.get("cargas")
                    ))
            conn.commit()

    def get_flat_results(self, filters=None):
        """Joins auctions and lots for a flat report."""
        query = """
            SELECT a.*, l.*
            FROM auctions a
            JOIN lots l ON a.identificador = l.auction_id
            WHERE 1=1
        """
        params = []
        if filters:
            if filters.get("provincia"):
                query += " AND l.bien_provincia LIKE ?"
                params.append(f"%{filters['provincia']}%")
            if filters.get("min_price"):
                query += " AND l.valor_subasta >= ?"
                params.append(filters["min_price"])
            if filters.get("max_price"):
                query += " AND l.valor_subasta <= ?"
                params.append(filters["max_price"])
            if filters.get("cp"):
                query += " AND l.bien_codigo_postal = ?"
                params.append(filters["cp"])

        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
