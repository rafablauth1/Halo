"""Registro de leituras de energia por ensaio/tensão — para acompanhar se o
medidor mantém a leitura correta antes/depois de cada evento de imunidade
EMC (mesma prática da planilha "Registro_Energia" usada no laboratório)."""

import json
from datetime import datetime, timezone

from emc.core.db import db_cursor

# Códigos padrão de grandezas usadas por medidores eletrônicos de energia no
# Brasil (numeração "códigos ABNT", referenciada em normas de concessionárias
# como Celesc E-321.0010 e em manuais de fabricante como o KS70). Não é
# proprietário de nenhum medidor específico — nem todo medidor implementa
# todos os códigos; o operador pode ignorar os que não existirem no seu.
ENERGY_CODES = [
    (1, "Data atual"),
    (2, "Hora atual"),
    (3, "Energia ativa total (kWh)"),
    (4, "Energia ativa Ponta (kWh)"),
    (6, "Energia ativa Reservado (kWh)"),
    (8, "Energia ativa Fora Ponta (kWh)"),
    (9, "Energia ativa Posto D (kWh)"),
    (10, "Demanda ativa máxima Ponta (kW)"),
    (11, "Hora da demanda máxima Posto D"),
    (12, "Demanda ativa máxima Reservado (kW)"),
    (13, "Data da demanda máxima Posto D"),
    (14, "Demanda ativa máxima Fora Ponta (kW)"),
    (15, "Demanda ativa máxima Posto D (kW)"),
    (16, "Demanda ativa último intervalo (kW)"),
    (17, "Demanda ativa acumulada Ponta (kW)"),
    (18, "Hora da demanda máxima Reservado"),
    (19, "Demanda ativa acumulada Reservado (kW)"),
    (20, "Data da demanda máxima Reservado"),
    (21, "Demanda ativa acumulada Fora Ponta (kW)"),
    (22, "Demanda ativa acumulada Posto D (kW)"),
    (23, "Número de resets de demanda"),
    (24, "Energia reativa indutiva total (kvarh)"),
    (25, "Energia reativa indutiva Ponta (kvarh)"),
    (26, "Hora da demanda máxima Fora Ponta"),
    (27, "Energia reativa indutiva Reservado (kvarh)"),
    (28, "Data da demanda máxima Fora Ponta"),
    (29, "Energia reativa indutiva Fora Ponta (kvarh)"),
    (30, "Energia reativa indutiva Posto D (kvarh)"),
    (31, "Energia reativa capacitiva total (kvarh)"),
    (32, "Status da bateria"),
    (33, "Número de série do medidor"),
    (34, "Demanda reativa indutiva máxima Ponta (kvar)"),
    (36, "Demanda reativa indutiva máxima Reservado (kvar)"),
    (37, "Hora da demanda máxima Ponta"),
    (38, "Demanda reativa indutiva máxima Fora Ponta (kvar)"),
    (39, "Demanda reativa indutiva máxima Posto D (kvar)"),
    (40, "Demanda reativa indutiva último intervalo (kvar)"),
    (41, "Demanda reativa indutiva acumulada Ponta (kvar)"),
    (42, "Data da demanda máxima Ponta"),
    (43, "Demanda reativa indutiva acumulada Reservado (kvar)"),
    (45, "Demanda reativa indutiva acumulada Fora Ponta (kvar)"),
    (46, "Demanda reativa indutiva acumulada Posto D (kvar)"),
    (47, "Demanda ativa intervalo atual (kW)"),
    (48, "Demanda reativa indutiva intervalo atual (kvar)"),
    (49, "Demanda reativa capacitiva intervalo atual (kvar)"),
    (50, "Energia ativa tarifa única (kWh)"),
    (51, "Demanda ativa máxima tarifa única (kW)"),
    (52, "Demanda ativa máxima total (kW)"),
    (53, "Demanda ativa acumulada tarifa única (kW)"),
    (54, "Demanda ativa acumulada total (kW)"),
    (62, "Demanda reativa indutiva máxima total (kvar)"),
    (65, "UFER total"),
    (66, "UFER Ponta"),
    (67, "UFER Reservado"),
    (68, "UFER Fora Ponta"),
    (69, "DMCR Ponta"),
    (70, "DMCR Reservado"),
    (71, "DMCR Fora Ponta"),
    (72, "DMCR tarifa única"),
    (73, "DMCR acumulado Ponta"),
    (74, "DMCR acumulado Reservado"),
    (75, "DMCR acumulado Fora Ponta"),
    (76, "UFER tarifa única"),
    (77, "DMCR tarifa única (kW)"),
    (78, "DMCR máximo total"),
    (79, "DMCR acumulado tarifa única"),
    (80, "DMCR acumulado total"),
    (85, "Energia reativa capacitiva Ponta (kvarh)"),
    (86, "Energia reativa capacitiva Reservado (kvarh)"),
    (87, "Energia reativa capacitiva Fora Ponta (kvarh)"),
    (88, "Teste do mostrador"),
    (89, "Energia reativa capacitiva Posto D (kvarh)"),
    (90, "UFER Posto D"),
    (91, "DMCR Posto D"),
    (92, "DMCR acumulado Posto D"),
    (93, "Fator de potência último intervalo"),
    (96, "Constante do TP (transformador de potencial)"),
    (97, "Constante do TC (transformador de corrente)"),
    (99, "Código de consistência"),
    (103, "Energia ativa reversa total (kWh) — injetada na rede"),
    (104, "Energia ativa reversa Ponta (kWh)"),
    (106, "Energia ativa reversa Reservado (kWh)"),
    (108, "Energia ativa reversa Fora Ponta (kWh)"),
    (109, "Energia ativa reversa Posto D (kWh)"),
    (116, "Demanda ativa reversa último intervalo (kW)"),
    (124, "Energia reativa indutiva reversa total (kvarh)"),
    (125, "Energia reativa indutiva reversa Ponta (kvarh)"),
    (127, "Energia reativa indutiva reversa Reservado (kvarh)"),
    (129, "Energia reativa indutiva reversa Fora Ponta (kvarh)"),
    (130, "Energia reativa indutiva reversa Posto D (kvarh)"),
    (131, "Energia reativa capacitiva reversa total (kvarh)"),
    (140, "Demanda reativa indutiva reversa último intervalo (kvar)"),
    (147, "Demanda ativa reversa intervalo atual (kW)"),
    (148, "Demanda reativa indutiva reversa intervalo atual (kvar)"),
    (149, "Demanda reativa capacitiva reversa intervalo atual (kvar)"),
    (189, "Energia reativa capacitiva reversa Posto D (kvarh)"),
]

def seed_energy_codes() -> None:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) c FROM energy_codes")
        if cur.fetchone()["c"] > 0:
            return
        cur.executemany(
            "INSERT INTO energy_codes (codigo, legenda) VALUES (?, ?)", ENERGY_CODES
        )


def list_codes() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT codigo, legenda FROM energy_codes ORDER BY codigo")
        return [dict(row) for row in cur.fetchall()]


def get_legend(codigo: int) -> str:
    with db_cursor() as cur:
        cur.execute("SELECT legenda FROM energy_codes WHERE codigo = ?", (codigo,))
        row = cur.fetchone()
        return row["legenda"] if row else ""


def replace_codes(codes: list[tuple[int, str]]) -> None:
    """Substitui o catálogo inteiro — usado pelo diálogo 'Gerenciar códigos'
    para adicionar/remover entradas."""
    with db_cursor() as cur:
        cur.execute("DELETE FROM energy_codes")
        cur.executemany("INSERT INTO energy_codes (codigo, legenda) VALUES (?, ?)", codes)


def get_leituras(project_id: int) -> list[dict]:
    """As leituras de energia do projeto — identificação do equipamento (fabricante,
    protocolo etc.) agora fica no Cadastro (app.core.planner), não aqui."""
    with db_cursor() as cur:
        cur.execute("SELECT data_json FROM energy_registries WHERE project_id = ?", (project_id,))
        row = cur.fetchone()
    if row is None:
        return []
    return json.loads(row["data_json"]).get("leituras", [])


def save_leituras(project_id: int, leituras: list) -> None:
    data_json = json.dumps({"leituras": leituras}, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    with db_cursor() as cur:
        cur.execute("SELECT id FROM energy_registries WHERE project_id = ?", (project_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE energy_registries SET data_json = ?, updated_at = ? WHERE project_id = ?",
                (data_json, now, project_id),
            )
        else:
            cur.execute(
                "INSERT INTO energy_registries (project_id, data_json, updated_at) VALUES (?, ?, ?)",
                (project_id, data_json, now),
            )
