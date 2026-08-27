"""
core/evaluation.py

Compara um Trace (ja corrigido) com uma StandardMethod e calcula, para
cada detector definido na norma: a margem ponto-a-ponto (limite - nivel)
e o pior caso (menor margem = ponto mais critico).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.limits import StandardMethod
from core.trace import Trace


@dataclass
class EvaluationResult:
    detector: str
    freq_hz: np.ndarray
    trace_level: np.ndarray
    limit_level: np.ndarray  # NaN onde o limite nao esta definido/verificado
    margin_db: np.ndarray  # limit - trace (positivo = passa, negativo = falha)
    worst_margin_db: float
    worst_freq_hz: float
    has_undefined_limit: bool
    # Detector que de fato produziu os niveis usados nesta avaliacao. Quando
    # difere de `detector`, o resultado nao e uma medicao direta daquele
    # detector -- ver `regra_4_1`.
    measured_detector: str = ""
    # True quando este resultado sai do atalho do item 4.1 da CISPR 15: o
    # nivel foi medido em quase-pico e comparado com o limite de media.
    regra_4_1: bool = False

    @property
    def verdict(self) -> str:
        if self.has_undefined_limit and np.all(np.isnan(self.margin_db)):
            return "INDEFINIDO (limite nao carregado/verificado)"
        if np.isnan(self.worst_margin_db):
            return "INDEFINIDO"
        if self.regra_4_1:
            # CISPR 15 item 4.1: medido em QP e atendendo ao limite de media,
            # ambos os limites estao atendidos e nao precisa medir em media.
            # Se NAO atende, nada se conclui sobre a media -- o nivel de QP e
            # so um limite superior do de media. Tem que medir com o detector.
            if self.worst_margin_db >= 0:
                return "APROVADO (item 4.1)"
            return "INDETERMINADO (medir com detector de media)"
        return "APROVADO" if self.worst_margin_db >= 0 else "REPROVADO"


def evaluate(trace: Trace, method: StandardMethod,
              incerteza=None,
              detector_traces: Optional[dict[str, Trace]] = None,
              regra_4_1: bool = True) -> list[EvaluationResult]:
    """Compara o trace com os limites da norma.

    `incerteza` (ConfiguracaoIncerteza, opcional) aplica a regra de decisao:
    o limite usado no veredito passa a ser o limite EFETIVO, ja com a banda
    de guarda que a regra exigir. Sem ele, compara direto com o limite --
    que e a regra de risco compartilhado.

    `detector_traces` permite dar um trace proprio para cada detector. Um
    detector que tenha o seu trace e avaliado com ele, direto.

    `regra_4_1` liga o atalho do item 4.1 da CISPR 15: quando existe limite
    de media mas NAO existe medicao de media, o nivel de quase-pico e usado
    como limite superior. Se ele ja atende o limite de media, ambos estao
    atendidos; se nao atende, o resultado e INDETERMINADO (e nao reprovado),
    porque o valor de media real e menor ou igual ao de quase-pico."""
    detector_traces = detector_traces or {}
    results = []
    for limit_line in method.limit_lines:
        det = limit_line.detector

        # De onde saem os niveis deste detector?
        proprio = detector_traces.get(det)
        if proprio is not None:
            niveis = np.interp(trace.freq_hz, proprio.freq_hz, proprio.level)
            medido_por = det
            usa_regra_4_1 = False
        else:
            niveis = trace.level
            medido_por = trace.detector or "desconhecido"
            # Atalho do item 4.1: nivel de quase-pico usado contra limite de media
            usa_regra_4_1 = bool(
                regra_4_1 and det in ("AV", "CAV")
                and medido_por.upper() in ("QP", "PK")
            )

        # value_at retorna None fora de faixa/nao definido -> converte p/ NaN
        limit_vals = np.array([np.nan if v is None else v for v in
                                [limit_line.value_at(f) for f in trace.freq_hz]])
        # A regra de decisao pode reduzir o limite (banda de guarda). O
        # veredito sai do limite EFETIVO; o limite de norma continua sendo
        # o que aparece no grafico.
        if incerteza is not None:
            limit_efetivo = incerteza.limite_efetivo(trace.freq_hz, limit_vals)
        else:
            limit_efetivo = limit_vals
        margin = limit_efetivo - niveis
        has_undef = bool(np.any(np.isnan(limit_vals)))
        if np.all(np.isnan(margin)):
            worst_margin = float("nan")
            worst_freq = float("nan")
        else:
            idx = int(np.nanargmin(margin))
            worst_margin = float(margin[idx])
            worst_freq = float(trace.freq_hz[idx])
        results.append(EvaluationResult(
            detector=det,
            freq_hz=trace.freq_hz,
            trace_level=niveis,
            limit_level=limit_vals,
            margin_db=margin,
            worst_margin_db=worst_margin,
            worst_freq_hz=worst_freq,
            has_undefined_limit=has_undef,
            measured_detector=medido_por,
            regra_4_1=usa_regra_4_1,
        ))
    return results


@dataclass
class PeakResult:
    """Um pico detectado no traco, com o nivel medido comparado contra o
    limite de cada detector da norma naquela frequencia -- no mesmo formato
    da tabela 'Picos Detectados' dos relatorios do RadiMation.

    `levels` guarda o nivel POR DETECTOR: num ensaio real o mesmo pico tem
    um valor de Average e outro de Quasi-Peak (QP >= AV sempre), medidos
    em varreduras/traces distintos. Quando so existe um trace, todos os
    detectores usam o mesmo valor (`level`)."""
    freq_hz: float
    level: float
    levels: dict[str, float] = field(default_factory=dict)
    limits: dict[str, Optional[float]] = field(default_factory=dict)
    diffs: dict[str, Optional[float]] = field(default_factory=dict)  # nivel - limite (negativo = passa)
    status: str = "Pass"

    # Detectores cujo nivel veio do atalho do item 4.1 (medido em QP,
    # comparado com limite de media). Nesses, ultrapassar o limite NAO e
    # reprovacao -- e indeterminacao.
    indeterminados: list[str] = field(default_factory=list)

    def level_for(self, detector: str) -> float:
        return self.levels.get(detector, self.level)


def _prominences(level: np.ndarray, candidates: np.ndarray, window: int) -> np.ndarray:
    """Proeminencia de cada maximo local: o quanto ele se destaca do vale
    mais alto ao seu redor, dentro de uma janela. E o que separa um pico de
    emissao de verdade da ondulacao do piso de ruido."""
    out = np.empty(len(candidates), dtype=float)
    n = len(level)
    for k, idx in enumerate(candidates):
        lo = max(0, idx - window)
        hi = min(n, idx + window + 1)
        left_min = level[lo:idx + 1].min()
        right_min = level[idx:hi].min()
        out[k] = level[idx] - max(left_min, right_min)
    return out


def detect_peaks(trace: Trace, method: StandardMethod,
                  margin_db: Optional[float] = None,
                  min_log_spacing: float = 0.02,
                  max_peaks: Optional[int] = None,
                  min_prominence_db: float = 10.0,
                  detector_traces: Optional[dict[str, Trace]] = None,
                  regra_4_1: bool = True) -> list[PeakResult]:
    """Encontra os picos de emissao do traco e avalia CADA UM contra o
    limite -- todos entram na tabela numerados, tanto os que passam quanto
    os que excedem o limite.

    Um maximo local so conta como pico se tiver `min_prominence_db` de
    proeminencia (destaque sobre o vale ao redor); isso descarta a
    ondulacao do piso de ruido sem descartar emissao real. `max_peaks=None`
    (padrao) lista todos os picos encontrados; passe um numero para cortar
    nos N maiores.

    `margin_db` e opcional e restringe a lista aos picos dentro de X dB do
    limite (ou acima) -- e o criterio da MEDICAO FINAL (quem e remedido em
    QP/AV), nao o da tabela.

    `detector_traces` permite passar um trace por detector (ex.: o trace de
    Average e o de Quasi-Peak medidos na mesma varredura). Sem ele, todos
    os detectores usam o nivel do trace principal.

    Picos redundantes muito proximos em frequencia sao suprimidos
    (non-max-suppression em escala log)."""
    freq = trace.freq_hz
    level = trace.level
    n = len(freq)
    if n < 3 or not method.limit_lines:
        return []

    is_max = np.zeros(n, dtype=bool)
    is_max[1:-1] = (level[1:-1] > level[:-2]) & (level[1:-1] > level[2:])
    candidates = np.nonzero(is_max)[0]
    if len(candidates) == 0:
        return []

    # Um maximo local entra na lista se (a) tiver proeminencia suficiente
    # para ser emissao de verdade e nao ondulacao do piso de ruido, OU
    # (b) exceder algum limite da norma -- neste caso entra sempre, por
    # menor que seja a proeminencia: uma reprovacao nunca pode sumir da
    # tabela por causa de um criterio de deteccao.
    window = max(5, n // 200)
    prom = _prominences(level, candidates, window)
    exceeds = np.array([
        any((lim := ll.value_at(freq[idx])) is not None and level[idx] > lim
            for ll in method.limit_lines)
        for idx in candidates
    ], dtype=bool)
    candidates = candidates[(prom >= min_prominence_db) | exceeds]

    if margin_db is None:
        kept = list(candidates)
    else:
        kept = []
        for idx in candidates:
            f, lvl = freq[idx], level[idx]
            for ll in method.limit_lines:
                lim = ll.value_at(f)
                if lim is not None and lvl >= lim - margin_db:
                    kept.append(idx)
                    break

    kept.sort(key=lambda i: level[i], reverse=True)
    log_freq = np.log10(np.maximum(freq, 1e-9))
    selected: list[int] = []
    for idx in kept:
        if all(abs(log_freq[idx] - log_freq[s]) > min_log_spacing for s in selected):
            selected.append(idx)
        if max_peaks is not None and len(selected) >= max_peaks:
            break
    selected.sort(key=lambda i: freq[i])

    results = []
    for idx in selected:
        f, lvl = float(freq[idx]), float(level[idx])
        levels: dict[str, float] = {}
        limits: dict[str, Optional[float]] = {}
        diffs: dict[str, Optional[float]] = {}
        indeterminados: list[str] = []
        status = "Pass"
        medido_por = (trace.detector or "").upper()
        for ll in method.limit_lines:
            det = ll.detector
            # nivel daquele detector: do trace proprio dele, se houver
            det_trace = (detector_traces or {}).get(det)
            if det_trace is not None:
                det_level = float(det_trace.value_at(f))
                por_regra_4_1 = False
            else:
                det_level = lvl
                # item 4.1: QP comparado com limite de media
                por_regra_4_1 = (regra_4_1 and det in ("AV", "CAV")
                                  and medido_por in ("QP", "PK"))
            levels[det] = det_level
            lim = ll.value_at(f)
            limits[det] = lim
            if lim is not None:
                diff = det_level - lim
                diffs[det] = diff
                if diff > 0:
                    if por_regra_4_1:
                        # nao reprova: o nivel de media real e <= o de QP
                        indeterminados.append(det)
                        if status == "Pass":
                            status = "Indet."
                    else:
                        status = "Fail"
            else:
                diffs[det] = None
        results.append(PeakResult(freq_hz=f, level=lvl, levels=levels,
                                   limits=limits, diffs=diffs, status=status,
                                   indeterminados=indeterminados))
    return results
