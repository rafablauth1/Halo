import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from emc import config
from emc.core.db import db_cursor

MIRROR_FILENAME = "roteiros_execucao.json"


def save_template(standard_code: str, name: str, level_label: str, params: dict) -> int:
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO templates (standard_code, name, level_label, params_json, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                standard_code,
                name,
                level_label,
                json.dumps(params),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        template_id = cur.lastrowid
    _push_to_mirror()
    return template_id


def list_templates(standard_code: str) -> list[dict]:
    _pull_from_mirror()
    _push_to_mirror()
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM templates WHERE standard_code = ? ORDER BY name",
            (standard_code,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["params"] = json.loads(row["params_json"])
    return rows


def get_template(template_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
        row = cur.fetchone()
    if row is None:
        return None
    data = dict(row)
    data["params"] = json.loads(data["params_json"])
    return data


def delete_template(template_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    _push_to_mirror()


# ---- espelhamento (roteiros salvos em duplicidade: local + pasta de rede) ----
# O roteiro de ensaio (template) precisa estar disponível tanto no PC portátil
# (que às vezes fica sem rede) quanto no PC "normal"/outros PCs do laboratório
# — por isso, além de gravar no banco local (sempre funciona, mesmo offline),
# espelha um snapshot em JSON numa pasta configurável (tipicamente de rede).
# Ao carregar a lista, primeiro puxa do espelho qualquer roteiro que exista lá
# mas não localmente (import), depois some com o que já tem localmente. Não
# resolve conflito de edição — só preenche o que falta de um lado pro outro.


def _mirror_path() -> Optional[Path]:
    mirror_dir = config.get_templates_mirror_dir()
    if mirror_dir is None:
        return None
    return mirror_dir / MIRROR_FILENAME


def _all_templates_raw() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM templates ORDER BY standard_code, name")
        return [dict(row) for row in cur.fetchall()]


def _pull_from_mirror() -> None:
    """Importa pro banco local qualquer roteiro que exista no espelho mas não
    localmente (identificado por standard_code + name) — assim um roteiro
    salvo em OUTRO PC aparece aqui na próxima vez que a lista for aberta."""
    path = _mirror_path()
    if path is None or not path.exists():
        return
    try:
        mirror_entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    local = _all_templates_raw()
    local_keys = {(r["standard_code"], r["name"]) for r in local}

    with db_cursor() as cur:
        for entry in mirror_entries:
            key = (entry.get("standard_code"), entry.get("name"))
            if key in local_keys or not all(key):
                continue
            cur.execute(
                """INSERT INTO templates (standard_code, name, level_label, params_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    entry["standard_code"],
                    entry["name"],
                    entry.get("level_label", ""),
                    json.dumps(entry["params"]),
                    entry.get("created_at") or datetime.now(timezone.utc).isoformat(),
                ),
            )


def _push_to_mirror() -> None:
    """Grava no espelho (se configurado) todos os roteiros do banco local —
    sobrescreve o arquivo inteiro com o estado atual local, já mesclado com
    o que o espelho já tinha (via _pull_from_mirror, chamado antes)."""
    path = _mirror_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for row in _all_templates_raw():
            entries.append(
                {
                    "standard_code": row["standard_code"],
                    "name": row["name"],
                    "level_label": row["level_label"],
                    "params": json.loads(row["params_json"]),
                    "created_at": row["created_at"],
                }
            )
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # rede fora do ar/inacessível — o roteiro já está salvo localmente, só não espelhou agora
