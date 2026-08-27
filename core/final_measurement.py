"""
core/final_measurement.py

Resultado da MEDICAO FINAL: o nivel de cada pico remedido com o detector
de norma (quase-pico, media...), em frequencia fixa.

Por que isso existe separado do Trace
-------------------------------------
O prescan e uma varredura: milhares de pontos, detector de pico, rapido e
impreciso. A medicao final e o oposto -- meia duzia de frequencias, uma de
cada vez, com o detector e o tempo de medicao que a norma manda. Sao dois
tipos de dado diferentes:

* o prescan e uma CURVA, e vira `Trace`;
* a medicao final e um conjunto de PONTOS soltos, e vira `MedicaoFinal`.

Guardar os pontos finais como se fossem um Trace esparso daria um grafico
errado -- o programa desenharia retas ligando um pico ao outro, como se
houvesse emissao medida no meio. Por isso eles sao desenhados como
marcadores, e a tabela usa o valor final no lugar do valor do prescan.

A CISPR 15 nao define esse fluxo; ele vem da pratica de medicao (CISPR
16-2-1) e e o que o RadiMation faz: prescan em pico -> reducao de dados
(escolhe os picos) -> medicao final em QP/media nas frequencias escolhidas.
O valor final costuma ficar ABAIXO do prescan, porque o detector de pico
responde ao maximo instantaneo e o quase-pico/media ponderam no tempo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PontoFinal:
    """Uma frequencia remedida, com um nivel por detector."""
    freq_hz: float
    niveis: dict[str, float] = field(default_factory=dict)   # detector -> dB
    # nivel que o prescan tinha nesta frequencia, para comparacao
    nivel_prescan: Optional[float] = None
    observacao: str = ""

    def delta_prescan(self, detector: str) -> Optional[float]:
        """Quanto o valor final ficou abaixo do prescan (negativo = abaixo).
        E o numero que denuncia problema: quase-pico ACIMA do pico do
        prescan e fisicamente impossivel e indica erro de configuracao."""
        if self.nivel_prescan is None or detector not in self.niveis:
            return None
        return self.niveis[detector] - self.nivel_prescan


@dataclass
class MedicaoFinal:
    """Conjunto de pontos remedidos, com a procedencia da medicao."""
    pontos: list[PontoFinal] = field(default_factory=list)
    detectores: list[str] = field(default_factory=list)
    unidade: str = "dBuV"
    instrumento: str = ""
    simulada: bool = False
    quando: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    # tempo de medicao/observacao efetivamente usado, por detector
    tempos: dict[str, tuple[float, float]] = field(default_factory=dict)

    # tolerancia para casar a frequencia de um pico com a de um ponto
    # medido: o receiver arredonda a sintonia para o passo dele, entao os
    # valores nao voltam identicos ao que foi pedido
    TOL_RELATIVA = 1e-4

    def nivel(self, freq_hz: float, detector: str) -> Optional[float]:
        """Nivel final naquela frequencia e detector, ou None se este pico
        nao foi remedido (fica de fora quando esta longe do limite)."""
        p = self.ponto_em(freq_hz)
        if p is None:
            return None
        return p.niveis.get(detector)

    def ponto_em(self, freq_hz: float) -> Optional[PontoFinal]:
        if not self.pontos:
            return None
        melhor, menor = None, None
        for p in self.pontos:
            d = abs(p.freq_hz - freq_hz)
            if menor is None or d < menor:
                melhor, menor = p, d
        if melhor is None:
            return None
        tol = max(abs(freq_hz) * self.TOL_RELATIVA, 1.0)
        return melhor if menor <= tol else None

    def inconsistencias(self) -> list[str]:
        """Avisos fisicos. Quase-pico nunca pode passar do pico, e a media
        nunca pode passar do quase-pico; se passar, a configuracao do
        receiver (tempo de medicao, atenuacao, sobrecarga) esta errada."""
        avisos = []
        for p in self.pontos:
            pk = p.nivel_prescan
            qp = p.niveis.get("QP")
            av = p.niveis.get("AV") if "AV" in p.niveis else p.niveis.get("CAV")
            f = p.freq_hz / 1e6
            if pk is not None and qp is not None and qp > pk + 0.5:
                avisos.append(
                    f"{f:.3f} MHz: quase-pico ({qp:.1f}) acima do pico do "
                    f"prescan ({pk:.1f}) — confira tempo de medicao e atenuacao")
            if qp is not None and av is not None and av > qp + 0.5:
                avisos.append(
                    f"{f:.3f} MHz: media ({av:.1f}) acima do quase-pico "
                    f"({qp:.1f}) — fisicamente impossivel")
        return avisos

    def resumo(self) -> str:
        if not self.pontos:
            return "Nenhum pico remedido."
        dets = ", ".join(self.detectores) or "—"
        marca = " [SIMULADA]" if self.simulada else ""
        return (f"{len(self.pontos)} pico(s) remedido(s) em {dets}{marca} · "
                f"{self.quando.replace('T', ' ')}")
