"""Semeia templates oficiais de roteiro de ensaio extraídos de normas do INMETRO.
Chamado (de forma idempotente) toda vez que o banco é inicializado."""

from emc.core import templates

NIT_SEGEL_044_NAME = "NIT-SEGEL-044 (medidores de energia elétrica)"


def seed_default_templates() -> None:
    _seed_burst()
    _seed_surge()
    _seed_dips()


def _seed_if_missing(standard_code: str, name: str, level_label: str, params: dict) -> None:
    existing = templates.list_templates(standard_code)
    if any(t["name"] == name for t in existing):
        return
    templates.save_template(standard_code, name, level_label, params)


def _seed_burst() -> None:
    # NIT-SEGEL-044 §9.3.2.1: circuito de tensão 4 kV, 60 s por polaridade, 5kHz (taxa padrão EFT).
    # Circuitos auxiliares >40V usam 2kV e <40V usam 1kV — ajustar manualmente nesses casos.
    _seed_if_missing(
        "4-4",
        NIT_SEGEL_044_NAME,
        "§9.3 — circuito de tensão 4 kV (aux. >40V: 2kV; aux. <40V: 1kV — ajustar manualmente)",
        {
            "points": [
                {
                    "voltage": 4000,
                    "frequency_hz": 5000,
                    "coupling": "COM",
                    "polarity": polarity,
                    "duration_s": 60,
                }
                for polarity in ("+", "-")
            ]
        },
    )


def _seed_surge() -> None:
    # NIT-SEGEL-044 §9.2.3.3 (instrumento com neutro e PE): nível de severidade especificado é o
    # nível 4 — 2kV entre linhas (Zfonte=2ohm) e 4kV entre linha e terra (Zfonte=12ohm). Todos os
    # níveis inferiores (0,5/1/2 kV) também devem ser ensaiados conforme item 8 da IEC 61000-4-5 —
    # usar os presets de nível na tela para os níveis intermediários.
    _seed_if_missing(
        "4-5",
        f"{NIT_SEGEL_044_NAME} — L-N 2kV (nível 4)",
        "§9.2.3.3.a — entre linhas, 2kV, Zfonte=2Ω",
        {
            "points": [
                {
                    "voltage": 2000,
                    "coupling": "L-N",
                    "polarity": polarity,
                    "phase_angle": angle,
                    "pulse_count": 1,
                    "interval_s": 60,
                }
                for polarity in ("+", "-")
                for angle in (0, 90, 180, 270)
            ]
        },
    )
    _seed_if_missing(
        "4-5",
        f"{NIT_SEGEL_044_NAME} — L-PE 4kV (nível 4)",
        "§9.2.3.3.c — linha e terra, 4kV, Zfonte=12Ω",
        {
            "points": [
                {
                    "voltage": 4000,
                    "coupling": "L-PE",
                    "polarity": polarity,
                    "phase_angle": angle,
                    "pulse_count": 1,
                    "interval_s": 60,
                }
                for polarity in ("+", "-")
                for angle in (0, 90, 180, 270)
            ]
        },
    )


def _seed_dips() -> None:
    # NIT-SEGEL-044 Tabela 1 (item 9.6.3.2) — os 9 eventos oficiais para medidores de energia.
    # Duração em ciclos, como a norma define (não em ms — a app converte pra ms na hora de
    # executar, a partir da frequência do ensaio, 60Hz aqui). percent_un é % de QUEDA (o
    # quanto a tensão cai) — igual à "Redução de tensão" já publicada na Tabela 1, sem
    # conversão nenhuma. `count` é quantas vezes cada linha dispara seguida; `interval_cycles`
    # é a pausa em tensão nominal entre uma repetição e outra da mesma linha.
    events = [
        {"percent_un": 100, "cycles": 6, "count": 3, "interval_cycles": 3, "phase_angles": [0]},
        {"percent_un": 100, "cycles": 60, "count": 3, "interval_cycles": 3, "phase_angles": [0]},
        {"percent_un": 100, "cycles": 1, "phase_angles": [0]},
        {"percent_un": 95, "cycles": 300, "count": 3, "interval_cycles": 600, "phase_angles": [0]},
        {"percent_un": 60, "cycles": 6, "count": 3, "interval_cycles": 600, "phase_angles": [0]},
        {"percent_un": 60, "cycles": 60, "count": 3, "interval_cycles": 600, "phase_angles": [0]},
        {"percent_un": 30, "cycles": 0.5, "count": 3, "interval_cycles": 600, "phase_angles": [0, 180]},
        {"percent_un": 30, "cycles": 1, "count": 3, "interval_cycles": 600, "phase_angles": [0]},
        {"percent_un": 50, "cycles": 3600, "phase_angles": [0]},
    ]
    _seed_if_missing(
        "4-11",
        NIT_SEGEL_044_NAME,
        "Tabela 1 completa (9 eventos, rede 60Hz) — só ajustar a tensão nominal (Un)",
        {
            "nominal_voltage": 220,
            "frequency_hz": 60,
            "phase_angles": [0],
            "events": events,
        },
    )
