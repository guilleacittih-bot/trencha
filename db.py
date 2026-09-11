"""Almacenamiento mínimo en SQLite: qué ya se anunció y estado de las fuentes."""
from __future__ import annotations

import os
import sqlite3
import time


class DB:
    def __init__(self, ruta: str):
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        self.c = sqlite3.connect(ruta)
        self.c.executescript("""
            CREATE TABLE IF NOT EXISTS vistos (
                tipo  TEXT NOT NULL,
                clave TEXT NOT NULL,
                ts    INTEGER NOT NULL,
                PRIMARY KEY (tipo, clave)
            );
            CREATE TABLE IF NOT EXISTS estado (
                clave TEXT PRIMARY KEY,
                valor TEXT
            );
            CREATE TABLE IF NOT EXISTS cuentas_x (
                usuario TEXT COLLATE NOCASE PRIMARY KEY,
                modo    TEXT NOT NULL,          -- 'todo', 'cripto' u 'off' (desactivada)
                canal   TEXT,                   -- canal propio (opcional)
                ts      INTEGER NOT NULL
            );
        """)
        self.c.commit()

    def visto(self, tipo: str, clave: str, dentro_de_seg: float | None = None) -> bool:
        fila = self.c.execute("SELECT ts FROM vistos WHERE tipo=? AND clave=?", (tipo, clave)).fetchone()
        if not fila:
            return False
        return dentro_de_seg is None or (time.time() - fila[0]) < dentro_de_seg

    def marcar(self, tipo: str, clave: str):
        self.c.execute("INSERT OR REPLACE INTO vistos VALUES (?, ?, ?)", (tipo, clave, int(time.time())))
        self.c.commit()

    def get(self, clave: str, defecto=None):
        fila = self.c.execute("SELECT valor FROM estado WHERE clave=?", (clave,)).fetchone()
        return fila[0] if fila else defecto

    def set(self, clave: str, valor):
        self.c.execute("INSERT OR REPLACE INTO estado VALUES (?, ?)", (clave, str(valor)))
        self.c.commit()

    def limpiar(self, dias: int = 30):
        self.c.execute("DELETE FROM vistos WHERE ts < ?", (int(time.time() - dias * 86400),))
        self.c.commit()

    # ── cuentas de X agregadas con /add ──
    def guardar_cuenta_x(self, usuario: str, modo: str, canal: str | None = None):
        self.c.execute("INSERT OR REPLACE INTO cuentas_x VALUES (?, ?, ?, ?)",
                       (usuario, modo, canal, int(time.time())))
        self.c.commit()

    def borrar_cuenta_x(self, usuario: str):
        self.c.execute("DELETE FROM cuentas_x WHERE usuario = ?", (usuario,))
        self.c.commit()

    def cuentas_x(self) -> list[dict]:
        filas = self.c.execute("SELECT usuario, modo, canal FROM cuentas_x ORDER BY ts").fetchall()
        return [{"usuario": u, "modo": m, "canal": c} for u, m, c in filas]
