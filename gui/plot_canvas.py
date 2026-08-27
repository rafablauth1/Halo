from __future__ import annotations

import warnings

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from gui import theme


class PlotCanvas(FigureCanvasQTAgg):
    """Canvas do grafico.

    `show_figure` troca a figura interna preservando o widget Qt. Ao trocar,
    a figura nova vem com o tamanho em que foi construida (9x5,6 pol) e NAO
    com o tamanho do widget -- se nao ajustarmos, o desenho e recortado
    (os rotulos do eixo X somem embaixo). Por isso todo swap e todo resize
    passam por `_ajustar`, que redimensiona a figura para o widget e refaz
    as margens.
    """

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(9, 5.2), dpi=100, facecolor=theme.SURFACE)
        super().__init__(self.fig)
        self.setParent(parent)
        # numa tela 1366x768 sobra pouca altura; 220 px ainda
        # mostra o grafico inteiro gracas as margens minimas
        self.setMinimumHeight(220)
        self.setStyleSheet("background: transparent; border: none;")

    # Espaco minimo, em pixels, que precisa sobrar de cada lado dos eixos
    # para caber rotulo de escala + nome do eixo.
    _MARGEM_ESQ_PX = 62
    _MARGEM_DIR_PX = 14
    _MARGEM_BASE_PX = 52
    _MARGEM_TOPO_PX = 16

    def _ajustar(self, fig: Figure):
        larg_px = max(1, self.width())
        alt_px = max(1, self.height())
        dpr = self.device_pixel_ratio or 1.0
        fig.set_size_inches(larg_px * dpr / fig.dpi, alt_px * dpr / fig.dpi,
                             forward=False)

        # Em janelas baixas/estreitas o tight_layout DESISTE (so emite um
        # aviso) e deixa as margens que estavam la -- calculadas para uma
        # figura maior. O resultado e o grafico cortado embaixo: somem os
        # rotulos de frequencia e o "Frequencia (Hz)". Por isso, depois do
        # tight_layout, as margens sao FORCADAS a um minimo em pixels.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            try:
                fig.tight_layout(rect=(0, 0, 1, 1.0))
            except Exception:
                pass

        sp = fig.subplotpars
        topo_max = getattr(fig, "halo_top", 0.84)
        esq = max(sp.left, self._MARGEM_ESQ_PX / larg_px)
        dir_ = min(sp.right, 1.0 - self._MARGEM_DIR_PX / larg_px)
        base = max(sp.bottom, self._MARGEM_BASE_PX / alt_px)
        topo = min(topo_max, 1.0 - self._MARGEM_TOPO_PX / alt_px)
        # so aplica se ainda sobrar area de desenho (janela minuscula)
        if esq < dir_ and base < topo:
            fig.subplots_adjust(left=esq, right=dir_, bottom=base, top=topo)
            self._rarear_rotulos(fig, (dir_ - esq) * larg_px,
                                  (topo - base) * alt_px)

    _LARGURA_ROTULO_PX = 54   # "100 k" com folga, na fonte de 8 pt

    def _rarear_rotulos(self, fig: Figure, larg_area: float, alt_area: float):
        """Esconde rotulos do eixo X quando nao cabem lado a lado.

        Com a proporcao travada, numa janela baixa o eixo fica estreito e os
        oito rotulos da escala log (9 k, 30 k, 50 k, 100 k...) se atropelam.
        Aqui um a cada N e mantido -- as linhas de grade continuam todas no
        lugar, so o texto e que rareia."""
        if not fig.axes:
            return
        ax = fig.axes[0]
        # com box_aspect a area util encolhe para respeitar a proporcao
        r = ax.get_box_aspect()
        if r:
            largura = min(larg_area, alt_area / r) if r else larg_area
        else:
            largura = larg_area

        ticks = list(ax.get_xticks())
        if len(ticks) < 2:
            return
        cabem = max(2, int(largura // self._LARGURA_ROTULO_PX))
        passo = max(1, -(-len(ticks) // cabem))   # divisao para cima
        fmt = ax.xaxis.get_major_formatter()
        rotulos = [fmt(t, i) if i % passo == 0 else "" for i, t in enumerate(ticks)]
        # o ultimo rotulo (fim da faixa) e informacao demais para se perder
        if rotulos and not rotulos[-1]:
            rotulos[-1] = fmt(ticks[-1], len(ticks) - 1)
            if passo > 1 and len(rotulos) > 1 and rotulos[-2]:
                rotulos[-2] = ""
        ax.set_xticks(ticks)
        ax.set_xticklabels(rotulos)

    def show_figure(self, fig: Figure):
        old_fig = self.figure
        self.figure = fig
        fig.set_canvas(self)
        self._ajustar(fig)
        self.draw()
        del old_fig

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajustar(self.figure)
        self.draw_idle()
