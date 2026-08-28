"""Migração de roteiros salvos no formato antigo (parâmetro único + listas cartesianas)
para o formato novo baseado em pontos sequenciais (lista de "points"). Mantém templates
antigos utilizáveis depois da mudança do modelo de dados."""

from emc.core.standards import BURST_DEFAULT_DURATION_S, SURGE_DEFAULT_INTERVAL_S, SURGE_DEFAULT_PULSE_COUNT


def burst_params_to_points(params: dict) -> list[dict]:
    if "points" in params:
        return params["points"]
    voltage = params["voltage"]
    frequency_hz = params.get("frequency_hz", 5000)
    coupling = params.get("coupling", "COM")
    duration_s = params.get("duration_s", BURST_DEFAULT_DURATION_S)
    polarities = params.get("polarities", ["+", "-"]) or ["+"]
    return [
        {
            "voltage": voltage,
            "frequency_hz": frequency_hz,
            "coupling": coupling,
            "polarity": polarity,
            "duration_s": duration_s,
        }
        for polarity in polarities
    ]


def surge_params_to_points(params: dict) -> list[dict]:
    if "points" in params:
        return params["points"]
    voltage = params["voltage"]
    coupling = params.get("coupling", "L-N")
    pulse_count = params.get("pulse_count", SURGE_DEFAULT_PULSE_COUNT)
    interval_s = params.get("interval_s", SURGE_DEFAULT_INTERVAL_S)
    polarities = params.get("polarities", ["+", "-"]) or ["+"]
    phase_angles = params.get("phase_angles", [0, 90, 180, 270]) or [0]
    return [
        {
            "voltage": voltage,
            "coupling": coupling,
            "polarity": polarity,
            "phase_angle": angle,
            "pulse_count": pulse_count,
            "interval_s": interval_s,
        }
        for polarity in polarities
        for angle in phase_angles
    ]
