import json
from datetime import datetime, timezone
from typing import Optional

from emc.config import STANDARDS
from emc.core import project_files
from emc.core.db import db_cursor

# Ensaios que costumam ter uma linha de comunicação separada da linha de
# alimentação a testar (ex.: RS-485/óptico de um medidor de energia).
COMM_LINE_ELIGIBLE_STANDARDS = ("4-3", "4-4", "4-6")

PROJECT_HEADER_FIELDS = (
    "fabricante", "modelo", "classe", "serie",
    "tensao_nominal", "corrente_nominal", "protocolo",
    "data_entrada", "previsao_saida", "origem_dados",
)

PORTA_ALIMENTACAO = "alimentação"
PORTA_COMUNICACAO = "comunicação"

ORIGEM_SOFTWARE = "software"
ORIGEM_DISPLAY = "display"

PROJECT_STATUS_ATIVO = "ativo"
PROJECT_STATUS_FINALIZADO = "finalizado"


def _resolve_porta_items(code: str, comm_line_config: dict) -> list[tuple[str, Optional[str]]]:
    """Pra ensaios elegíveis a linha de comunicação (4-3/4-4/4-6), o operador
    escolhe Alimentação e/ou Comunicação de forma independente (não é mais
    'sempre alimentação + comunicação opcional'). comm_line_config[code] pode
    ter {"alimentacao": bool, "comunicacao": bool, "tipo_comunicacao": str}."""
    if code not in COMM_LINE_ELIGIBLE_STANDARDS:
        return [(PORTA_ALIMENTACAO, None)]
    cfg = comm_line_config.get(code, {})
    items: list[tuple[str, Optional[str]]] = []
    if cfg.get("alimentacao", True):
        items.append((PORTA_ALIMENTACAO, None))
    if cfg.get("comunicacao", False):
        items.append((PORTA_COMUNICACAO, cfg.get("tipo_comunicacao") or None))
    if not items:
        items.append((PORTA_ALIMENTACAO, None))
    return items


def create_project(
    name: str,
    client: str = "",
    standard_codes: Optional[list[str]] = None,
    header: Optional[dict] = None,
    comm_line_config: Optional[dict[str, dict]] = None,
    applicable_codes: Optional[list[int]] = None,
) -> int:
    """standard_codes: quais ensaios (4-2, 4-3, ...) se aplicam a este projeto —
    por padrão, todos os cobertos pela norma (STANDARDS). comm_line_config:
    dentre COMM_LINE_ELIGIBLE_STANDARDS, config por código com alimentacao/
    comunicacao (bool, independentes) e tipo_comunicacao (texto livre).
    applicable_codes: códigos de grandeza do catálogo que esse medidor específico
    tem (ex.: os que aparecem no display) — usado pra gerar leituras automaticamente."""
    created_at = datetime.now(timezone.utc).isoformat()
    codes = standard_codes if standard_codes is not None else list(STANDARDS)
    header = header or {}
    comm_line_config = comm_line_config or {}
    header_values = [header.get(field, "") for field in PROJECT_HEADER_FIELDS]
    codigos_json = json.dumps(applicable_codes or [])
    with db_cursor() as cur:
        cur.execute(
            f"""INSERT INTO projects (name, client, {', '.join(PROJECT_HEADER_FIELDS)}, codigos_json, created_at)
                VALUES (?, ?, {', '.join('?' for _ in PROJECT_HEADER_FIELDS)}, ?, ?)""",
            (name, client, *header_values, codigos_json, created_at),
        )
        project_id = cur.lastrowid
        for standard_code in codes:
            for porta, tipo_comunicacao in _resolve_porta_items(standard_code, comm_line_config):
                cur.execute(
                    """INSERT INTO test_items (project_id, standard_code, porta, tipo_comunicacao, status)
                       VALUES (?, ?, ?, ?, 'pendente')""",
                    (project_id, standard_code, porta, tipo_comunicacao),
                )
    project_files.get_project_folder(project_id)
    return project_id


def update_project(
    project_id: int, name: str, client: str, header: dict, applicable_codes: Optional[list[int]] = None
) -> None:
    header_values = [header.get(field, "") for field in PROJECT_HEADER_FIELDS]
    codigos_json = json.dumps(applicable_codes if applicable_codes is not None else get_applicable_codes(project_id))
    with db_cursor() as cur:
        cur.execute(
            f"""UPDATE projects SET name = ?, client = ?,
                {', '.join(f'{f} = ?' for f in PROJECT_HEADER_FIELDS)},
                codigos_json = ?
                WHERE id = ?""",
            (name, client, *header_values, codigos_json, project_id),
        )


def get_applicable_codes(project_id: int) -> list[int]:
    project = get_project(project_id)
    if not project or not project.get("codigos_json"):
        return []
    try:
        return json.loads(project["codigos_json"])
    except (json.JSONDecodeError, TypeError):
        return []


def set_project_standards(
    project_id: int, standard_codes: list[str], comm_line_config: Optional[dict[str, dict]] = None
) -> None:
    """Sincroniza os itens de checklist do projeto com a seleção de ensaios (usado ao
    editar o cadastro). Adiciona os que faltam; atualiza o tipo_comunicacao dos que já
    existem; remove só os que ainda estão pendentes e sem sessão vinculada — não apaga
    histórico de um ensaio já feito/agendado."""
    comm_line_config = comm_line_config or {}
    desired: dict[tuple[str, str], Optional[str]] = {}
    for code in standard_codes:
        for porta, tipo_comunicacao in _resolve_porta_items(code, comm_line_config):
            desired[(code, porta)] = tipo_comunicacao

    existing = list_test_items(project_id)
    existing_keys = {(item["standard_code"], item["porta"]) for item in existing}

    with db_cursor() as cur:
        for (code, porta), tipo_comunicacao in desired.items():
            if (code, porta) not in existing_keys:
                cur.execute(
                    """INSERT INTO test_items (project_id, standard_code, porta, tipo_comunicacao, status)
                       VALUES (?, ?, ?, ?, 'pendente')""",
                    (project_id, code, porta, tipo_comunicacao),
                )
            else:
                cur.execute(
                    "UPDATE test_items SET tipo_comunicacao = ? WHERE project_id = ? AND standard_code = ? AND porta = ?",
                    (tipo_comunicacao, project_id, code, porta),
                )
        for item in existing:
            key = (item["standard_code"], item["porta"])
            if key not in desired and item["status"] == "pendente" and item["session_id"] is None:
                cur.execute("DELETE FROM test_items WHERE id = ?", (item["id"],))


def delete_project(project_id: int) -> None:
    """Apaga o projeto e tudo que depende dele (itens de checklist, sessões,
    eventos, laudos, registro de energia) via ON DELETE CASCADE do schema."""
    with db_cursor() as cur:
        cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def finalize_project(project_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("UPDATE projects SET status = ? WHERE id = ?", (PROJECT_STATUS_FINALIZADO, project_id))


def reopen_project(project_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("UPDATE projects SET status = ? WHERE id = ?", (PROJECT_STATUS_ATIVO, project_id))


def list_projects() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


def list_active_projects() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC", (PROJECT_STATUS_ATIVO,)
        )
        return [dict(row) for row in cur.fetchall()]


def get_project(project_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_test_items(project_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_items WHERE project_id = ? ORDER BY standard_code",
            (project_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def list_scheduled_items() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT test_items.*, projects.name AS project_name
            FROM test_items
            JOIN projects ON projects.id = test_items.project_id
            WHERE test_items.scheduled_date IS NOT NULL
            ORDER BY test_items.scheduled_date
            """
        )
        return [dict(row) for row in cur.fetchall()]


def update_item_status(item_id: int, status: str) -> None:
    with db_cursor() as cur:
        cur.execute("UPDATE test_items SET status = ? WHERE id = ?", (status, item_id))


def update_item_schedule(item_id: int, scheduled_date: Optional[str]) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE test_items SET scheduled_date = ? WHERE id = ?", (scheduled_date, item_id)
        )


def link_item_session(item_id: int, session_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE test_items SET session_id = ?, status = 'concluido' WHERE id = ?",
            (session_id, item_id),
        )


def find_item(project_id: int, standard_code: str) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_items WHERE project_id = ? AND standard_code = ?",
            (project_id, standard_code),
        )
        row = cur.fetchone()
        return dict(row) if row else None
