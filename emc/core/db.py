import sqlite3
from contextlib import contextmanager

from emc.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client TEXT,
    fabricante TEXT,
    modelo TEXT,
    classe TEXT,
    serie TEXT,
    tensao_nominal TEXT,
    corrente_nominal TEXT,
    protocolo TEXT,
    data_entrada TEXT,
    previsao_saida TEXT,
    origem_dados TEXT,
    codigos_json TEXT,
    status TEXT NOT NULL DEFAULT 'ativo',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    standard_code TEXT NOT NULL,
    eut_name TEXT,
    eut_serial TEXT,
    operator TEXT,
    level_label TEXT,
    params_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS test_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    standard_code TEXT NOT NULL,
    porta TEXT NOT NULL DEFAULT 'alimentação',
    tipo_comunicacao TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    scheduled_date TEXT,
    session_id INTEGER REFERENCES test_sessions(id)
);

CREATE TABLE IF NOT EXISTS test_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_code TEXT NOT NULL,
    name TEXT NOT NULL,
    level_label TEXT,
    params_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS energy_registries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    fabricante TEXT,
    modelo TEXT,
    numero TEXT,
    serie TEXT,
    tensao_nominal TEXT,
    corrente_nominal TEXT,
    protocolo TEXT,
    data_entrada TEXT,
    previsao_saida TEXT,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS energy_codes (
    codigo INTEGER PRIMARY KEY,
    legenda TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Colunas adicionadas depois da criação inicial das tabelas — "CREATE TABLE IF
# NOT EXISTS" não adiciona coluna em tabela que já existe, então cada uma
# precisa ser migrada aqui (idempotente: só adiciona se ainda não existir).
_COLUMN_MIGRATIONS = {
    "projects": [
        ("fabricante", "TEXT"),
        ("modelo", "TEXT"),
        ("numero", "TEXT"),  # substituída por "classe" — mantida no schema pra não quebrar bancos antigos
        ("classe", "TEXT"),
        ("serie", "TEXT"),
        ("tensao_nominal", "TEXT"),
        ("corrente_nominal", "TEXT"),
        ("protocolo", "TEXT"),
        ("data_entrada", "TEXT"),
        ("previsao_saida", "TEXT"),
        ("origem_dados", "TEXT"),
        ("codigos_json", "TEXT"),
        ("status", "TEXT NOT NULL DEFAULT 'ativo'"),
    ],
    "test_items": [
        ("porta", "TEXT NOT NULL DEFAULT 'alimentação'"),
        ("tipo_comunicacao", "TEXT"),
    ],
}


def _run_column_migrations(conn: sqlite3.Connection) -> None:
    for table, columns in _COLUMN_MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, coltype in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _run_column_migrations(conn)
        conn.commit()
    finally:
        conn.close()
    from emc.core.energy_registry import seed_energy_codes
    from emc.core.seed_data import seed_default_templates

    seed_default_templates()
    seed_energy_codes()


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()
