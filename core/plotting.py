"""
core/plotting.py

Gera a figura matplotlib padrao: traco medido (corrigido) + linha(s)
de limite, eixo de frequencia em log, no estilo dos graficos que
softwares de EMC (RadiMation, EMC32 etc.) mostram na tela e no laudo.
Usado tanto pela GUI (embutido num FigureCanvas) quanto pelo gerador
de relatorio PDF (salvo como imagem).

Ha dois temas. O tema "light" e o do papel: fundo branco, grade preta
fina -- e o que vai para o PDF, identico ao grafico dos relatorios do
laboratório. O tema "dark" e so para a tela, para o grafico ficar integrado
a interface escura do programa; ele NAO e usado no relatorio.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, FixedLocator, LogLocator, NullFormatter

from core.evaluation import EvaluationResult, detect_peaks
from core.limits import StandardMethod
from core.trace import Trace

# Cores no mesmo esquema usado pelos relatorios do RadiMation: limite
# Quase-Pico em azul, limite Media em vermelho (linha grossa em degrau); a
# medicao real (traco do receiver) em verde, para se distinguir claramente
# das linhas de limite.
LIMIT_COLORS = {
    "QP": "#1f4e96",
    "AV": "#c0392b",
    "PK": "#7d3c98",
    "CISPR-AV": "#c0392b",
}
MEASURED_COLORS = {
    "QP": "#2e7d32",
    "PK": "#2e7d32",
    "AV": "#8b1a1a",
    "CISPR-AV": "#8b1a1a",
}
DEFAULT_LIMIT_COLOR = "#888888"
DEFAULT_MEASURED_COLOR = "#2e7d32"

# Variante para a tela escura: mesmas familias de cor (verde = medicao,
# azul = limite QP, vermelho = limite media), nos tons claros do esquema
# Material 3 escuro usado pela interface -- no fundo escuro quem carrega
# a cor e o tom claro, nao o saturado.
DARK_LIMIT_COLORS = {
    "QP": "#a6c8ff",       # M3 primary
    "AV": "#ffb4ab",       # M3 error
    "PK": "#d6bee4",       # M3 tertiary
    "CISPR-AV": "#ffb4ab",
}
DARK_MEASURED_COLORS = {
    "QP": "#4ade80",
    "PK": "#86efac",
    "AV": "#fdba74",
    "CISPR-AV": "#fdba74",
}

# Proporcao da caixa dos eixos no grafico do laudo (altura / largura),
# medida da propria figura de 9 x 5,6 pol: 8,09 x 4,16 pol de area util,
# ou seja 1,95 : 1. Na tela o cartao do grafico e largo e baixo; sem impor
# esta proporcao o traco fica esmagado num filete de 5 : 1, que nao e o que
# o operador esta acostumado a ver no RadiMation nem no laudo.
BOX_ASPECT_LAUDO = 0.5138

THEMES = {
    "light": {
        "fig_bg": "#ffffff",
        "ax_bg": "#ffffff",
        "grid_major": "#000000",
        "grid_minor": "#000000",
        "grid_major_lw": 0.4,
        "grid_minor_lw": 0.3,
        "spine": "#000000",
        "spine_lw": 1.1,
        "trace_lw": 0.4,     # espessura aprovada para o laudo -- nao mexer
        "limit_lw": 0.9,
        "mark_size": 6, "mark_lw": 1.4,
        "text": "#000000",
        "fail_marker": "#c0392b",
        "limits": LIMIT_COLORS,
        "measured": MEASURED_COLORS,
        "limit_default": DEFAULT_LIMIT_COLOR,
        "measured_default": DEFAULT_MEASURED_COLOR,
    },
    # Superficies do esquema Material 3 escuro, as mesmas da interface:
    # o fundo da figura e o do cartao (surface-container-low) e a area
    # dos eixos e a superficie mais baixa (surface-container-lowest).
    "dark": {
        "fig_bg": "#191c20",
        "ax_bg": "#0c0e13",
        "grid_major": "#4d525c",
        "grid_minor": "#31353d",
        "grid_major_lw": 0.6,
        "grid_minor_lw": 0.45,
        "spine": "#5a5f69",        # mesma linha das bordas da interface
        "spine_lw": 1.2,
        # Na tela o traco e o limite podem ser um pouco mais encorpados que
        # no papel: o monitor nao tem a resolucao da impressao, e a linha
        # de 0,4 pt some no fundo escuro. O laudo continua em 0,4 / 0,9.
        "trace_lw": 0.55,
        "limit_lw": 1.3,
        "mark_size": 7, "mark_lw": 1.6,
        "text": "#c3c6cf",         # M3 on-surface-variant
        "fail_marker": "#ffb4ab",
        "limits": DARK_LIMIT_COLORS,
        "measured": DARK_MEASURED_COLORS,
        "limit_default": "#8d9199",
        "measured_default": "#4ade80",
    },
}


def _freq_label(x: float) -> str:
    if x >= 1e6:
        return f"{x/1e6:g} M"
    if x >= 1e3:
        return f"{x/1e3:g} k"
    return f"{x:g}"


def _freq_formatter():
    return FuncFormatter(lambda x, _pos: _freq_label(x))


def _log_grid_locators(fmin: float, fmax: float) -> tuple[FixedLocator, FixedLocator]:
    """Replica a grade densa 'papel log' usada nos graficos de EMC
    (RadiMation/EMC32): ticks principais rotulados em 1/3/5 * 10^n (mais os
    proprios limites da faixa) e linhas de grade finas em cada multiplo
    inteiro de 2 a 9 dentro de cada decada, sem rotulo."""
    if fmin <= 0:
        fmin = 1.0
    dec_lo = int(np.floor(np.log10(fmin)))
    dec_hi = int(np.ceil(np.log10(fmax)))

    log_fmin, log_fmax = np.log10(fmin), np.log10(fmax)
    near_edge_gap = 0.05  # decadas de log10 -- evita rotulo colado no limite da faixa

    major = {fmin, fmax}
    minor = set()
    for dec in range(dec_lo, dec_hi + 1):
        base = 10.0 ** dec
        for sub in range(1, 10):
            pos = sub * base
            if not (fmin <= pos <= fmax):
                continue
            if sub in (1, 3, 5):
                if (abs(np.log10(pos) - log_fmin) < near_edge_gap or
                        abs(np.log10(pos) - log_fmax) < near_edge_gap):
                    continue  # muito perto do inicio/fim da faixa, rotulo colaria
                major.add(pos)
            else:
                minor.add(pos)
    return FixedLocator(sorted(major)), FixedLocator(sorted(minor))


def build_figure(trace: Trace, method: StandardMethod, results: list[EvaluationResult],
                  title: str | None = None,
                  detector_traces: dict[str, Trace] | None = None,
                  theme: str = "light",
                  show_title: bool = True,
                  box_aspect: float | None = None) -> Figure:
    """`theme='light'` (padrao) = grafico do laudo, fundo branco.
    `theme='dark'` = so para a tela do programa.

    `show_title=False` omite o titulo dentro da figura -- usado na tela,
    onde o nome do ensaio ja aparece na barra do cartao do grafico e
    repeti-lo so rouba altura util. O PDF sempre desenha o titulo.

    `box_aspect` trava a proporcao da caixa dos eixos (altura/largura).
    A tela usa BOX_ASPECT_LAUDO para o grafico sair com a MESMA forma do
    laudo, sobrando margem nas laterais quando o cartao e largo demais --
    e melhor sobrar margem do que achatar a curva."""
    tema = THEMES.get(theme, THEMES["light"])

    fig = Figure(figsize=(9, 5.6), dpi=120, facecolor=tema["fig_bg"])
    ax = fig.add_subplot(111, facecolor=tema["ax_bg"])
    if box_aspect:
        ax.set_box_aspect(box_aspect)

    # Desenha um traco por detector medido (Average, Quasi-Peak, Peak...),
    # como o RadiMation mostra. Sem `detector_traces`, so o trace principal.
    a_plotar = dict(detector_traces) if detector_traces else {}
    if not a_plotar:
        a_plotar = {trace.detector or "medicao": trace}
    for det, t in sorted(a_plotar.items(), key=lambda kv: kv[0]):
        if t is None:
            continue
        cor = tema["measured"].get(det, tema["measured_default"])
        ax.plot(t.freq_hz, t.level, color=cor, linewidth=tema["trace_lw"],
                label=f"Medicao ({det})")

    for ll in method.limit_lines:
        xs, ys = [], []
        for seg in ll.segments:
            xs += [seg.freq_start_hz, seg.freq_end_hz]
            ys += [seg.value_start, seg.value_end]
        xs = np.array(xs, dtype=float)
        ys = np.array([np.nan if y is None else y for y in ys], dtype=float)
        color = tema["limits"].get(ll.detector, tema["limit_default"])
        ax.plot(xs, ys, "-", color=color, linewidth=tema["limit_lw"],
                label=f"Limite {ll.detector} ({ll.unit})" + (" [NAO VERIFICADO]" if not ll.is_fully_verified() else ""))

    for peak in detect_peaks(trace, method):
        if peak.status == "Fail":
            ax.plot(peak.freq_hz, peak.level, "x", color=tema["fail_marker"],
                    markersize=tema["mark_size"],
                    markeredgewidth=tema["mark_lw"], zorder=5)

    fmin, fmax = method.freq_range_hz
    if method.x_axis == "linear":
        ax.set_xscale("linear")
    else:
        ax.set_xscale("log")
        major_loc, minor_loc = _log_grid_locators(fmin, fmax)
        ax.xaxis.set_major_locator(major_loc)
        ax.xaxis.set_minor_locator(minor_loc)
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.grid(True, which="minor", axis="x", linestyle="-",
                linewidth=tema["grid_minor_lw"], color=tema["grid_minor"])
    ax.xaxis.set_major_formatter(_freq_formatter())
    ax.set_xlim(fmin, fmax)
    ax.set_xlabel("Frequencia (Hz)", fontsize=9, color=tema["text"])
    unit = method.limit_lines[0].unit if method.limit_lines else "dB"
    ax.set_ylabel(f"Nivel ({unit})", fontsize=9, color=tema["text"])
    ax.grid(True, which="major", linestyle="-",
            linewidth=tema["grid_major_lw"], color=tema["grid_major"])
    ax.set_axisbelow(False)
    ax.tick_params(axis="both", labelsize=8, colors=tema["text"])
    for spine in ax.spines.values():
        spine.set_color(tema["spine"])
        spine.set_linewidth(tema["spine_lw"])

    if show_title and (title or method.title):
        ax.set_title(title or method.title, fontsize=9, pad=22, color=tema["text"])
    leg = ax.legend(fontsize=7, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=3,
                    frameon=False, borderaxespad=0.0)
    for txt in leg.get_texts():
        txt.set_color(tema["text"])
    # Fracao de altura reservada acima dos eixos (titulo + legenda). Sem
    # titulo sobra area util para o traco. O PlotCanvas le este valor ao
    # refazer as margens depois de redimensionar.
    fig.halo_top = 0.84 if show_title else 0.91
    fig.tight_layout(rect=(0, 0, 1, 1.0))
    fig.subplots_adjust(top=fig.halo_top)
    return fig
