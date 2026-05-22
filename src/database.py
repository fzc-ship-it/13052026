import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

STATUS_MAPPING = {
    "PU": "Próxima apertura",
    "EJ": "Celebrándose",
    "PC": "Concluida",
    "FS": "Finalizada",
    "CR": "Cesión de remate"
}

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
                    tipologia TEXT,
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

    def update_auction_status(self, identificador, new_status_code):
        status_desc = STATUS_MAPPING.get(new_status_code, new_status_code)
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE auctions SET estado_proceso = ?, last_updated = ? WHERE identificador = ?",
                           (status_desc, datetime.now().isoformat(), identificador))
            conn.commit()

    def get_auctions_by_status(self, status_descriptions):
        """Returns IDs and URLs of auctions in given statuses."""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(status_descriptions))
            cursor.execute(f"SELECT identificador, url, estado_proceso FROM auctions WHERE estado_proceso IN ({placeholders})", status_descriptions)
            return [dict(row) for row in cursor.fetchall()]

    def get_incomplete_auctions(self):
        """Identifies auctions with missing critical fields or no lot data."""
        query = """
            SELECT a.identificador, a.url
            FROM auctions a
            LEFT JOIN lots l ON a.identificador = l.auction_id
            WHERE l.id IS NULL
               OR a.fecha_inicio IS NULL OR a.fecha_inicio = ''
               OR a.fecha_conclusion IS NULL OR a.fecha_conclusion = ''
               OR a.autoridad_gestora_codigo IS NULL OR a.autoridad_gestora_codigo = ''
               OR l.bien_descripcion IS NULL OR l.bien_descripcion = ''
        """
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def _parse_price(self, value):
        if not value or not isinstance(value, str):
            return 0.0
        try:
            clean = value.replace("€", "").replace(".", "").replace(",", ".").strip()
            return float(clean)
        except (ValueError, AttributeError):
            return 0.0

    def save_full_auction(self, auction_data, status_code):
        identificador = auction_data.get("identificador")
        if not identificador:
            return

        estado_desc = STATUS_MAPPING.get(status_code, status_code)
        tiene_lotes = 1 if auction_data.get("lotes") and auction_data.get("lotes") != "Sin lotes" else 0

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

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
                auction_data.get("fecha_de_conclusion"),
                tiene_lotes,
                auction_data.get("codigo"),
                auction_data.get("telefono"),
                auction_data.get("correo_electronico"),
                estado_desc,
                json.dumps(auction_data),
                datetime.now().isoformat()
            ))

            cursor.execute("DELETE FROM lots WHERE auction_id = ?", (identificador,))

            lots_list = auction_data.get("lots_data", [])
            if not lots_list:
                cursor.execute("""
                    INSERT INTO lots
                    (auction_id, lote_numero, cantidad_reclamada, valor_subasta, tasacion,
                     puja_minima, importe_deposito, tramos_entre_pujas, bien_tipo, tipologia, bien_descripcion,
                     bien_direccion, bien_referencia_catastral, bien_idufir, bien_codigo_postal,
                     bien_localidad, bien_provincia, bien_vivienda_habitual, bien_situacion_posesoria,
                     bien_visitable, bien_cargas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    identificador,
                    0,
                    self._parse_price(auction_data.get("cantidad_reclamada")),
                    self._parse_price(auction_data.get("valor_subasta")),
                    self._parse_price(auction_data.get("tasacion")),
                    self._parse_price(auction_data.get("puja_minima")),
                    self._parse_price(auction_data.get("importe_del_deposito")),
                    auction_data.get("tramos_entre_pujas"),
                    auction_data.get("bien"),
                    auction_data.get("tipologia"),
                    auction_data.get("descripcion"),
                    auction_data.get("direccion"),
                    auction_data.get("referencia_catastral"),
                    auction_data.get("idufir"),
                    auction_data.get("codigo_postal"),
                    auction_data.get("localidad"),
                    auction_data.get("provincia"),
                    auction_data.get("vivienda_habitual"),
                    auction_data.get("situacion_posesoria"),
                    auction_data.get("visitable"),
                    auction_data.get("cargas")
                ))
            else:
                for lot in lots_list:
                    cursor.execute("""
                        INSERT INTO lots
                        (auction_id, lote_numero, cantidad_reclamada, valor_subasta, tasacion,
                         puja_minima, importe_deposito, tramos_entre_pujas, bien_tipo, tipologia, bien_descripcion,
                         bien_direccion, bien_referencia_catastral, bien_idufir, bien_codigo_postal,
                         bien_localidad, bien_provincia, bien_vivienda_habitual, bien_situacion_posesoria,
                        bien_visitable, bien_cargas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        identificador,
                        lot.get("lote_numero"),
                        self._parse_price(lot.get("cantidad_reclamada")),
                        self._parse_price(lot.get("valor_subasta")),
                        self._parse_price(lot.get("tasacion")),
                        self._parse_price(lot.get("puja_minima")),
                        self._parse_price(lot.get("importe_del_deposito")),
                        lot.get("tramos_entre_pujas"),
                        lot.get("bien"),
                        lot.get("tipologia"),
                        lot.get("descripcion"),
                        lot.get("direccion"),
                        lot.get("referencia_catastral"),
                        lot.get("idufir"),
                        lot.get("codigo_postal"),
                        lot.get("localidad"),
                        lot.get("provincia"),
                        lot.get("vivienda_habitual"),
                        lot.get("situacion_posesoria"),
                        lot.get("visitable"),
                        lot.get("cargas")
                    ))
            conn.commit()

    def get_flat_results(self, filters=None):
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
            if filters.get("estado_proceso"):
                query += " AND a.estado_proceso LIKE ?"
                params.append(f"%{filters['estado_proceso']}%")
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

    def get_status_counts(self):
        """Returns a summary of how many auctions are in each status."""
        query = "SELECT estado_proceso, COUNT(*) as count FROM auctions GROUP BY estado_proceso"
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            return {row['estado_proceso']: row['count'] for row in cursor.fetchall()}
