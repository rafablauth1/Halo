from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QPushButton, QComboBox, QLabel, QFileDialog,
                                QTableWidget, QTableWidgetItem, QMessageBox,
                                QDoubleSpinBox, QFormLayout, QGroupBox, QLineEdit,
                                QTabWidget, QListWidget, QListWidgetItem, QCheckBox,
                                QInputDialog, QScrollArea, QSplitter, QFrame,
                                QHeaderView, QAbstractItemView, QSizePolicy)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence

from core.limits import list_available_methods, load_method, StandardMethod
from core.trace import load_trace, Trace
from core.corrections import CorrectionTable, list_available_corrections, load_correction
from core.evaluation import evaluate, detect_peaks, EvaluationResult, PeakResult
from core.final_measurement import MedicaoFinal
from core.plotting import build_figure, BOX_ASPECT_LAUDO
from core.report import generate_pdf_report, ReportInfo
from gui import theme
from gui.widgets import (AppHeader, AppFooter, Badge, FitTable, Ladrilho,
                          VerdictBar, area_rolavel, desarmar_roda)
from gui.plot_canvas import PlotCanvas
from gui.limit_editor import LimitEditorDialog
from gui.standards_manager import StandardsManagerDialog
from gui.corrections_manager import CorrectionsManagerDialog
from gui.receiver_tab import ReceiverTab
from gui.equipamentos_tab import EquipamentosTab
from gui.dispositivos_tab import DispositivosTab
from core.equipamentos import (listar_equipamentos, carregar_equipamento,
                                aplicar_cadeia)
from core.dispositivos import GRUPOS
from core.incerteza import REGRAS, carregar as carregar_incerteza, salvar as salvar_incerteza
from gui.incerteza_dialog import IncertezaDialog

MANUAL_CORR_LABEL = "Manual (dB fixo, ver campo ao lado)"

# Mesmos rotulos/ordem de coluna do PDF (core/report.py).
_DETECTOR_LABELS = {"AV": "Average", "QP": "Quasi-Peak", "PK": "Peak",
                    "CAV": "CISPR Average", "CRMS": "RMS-Average", "RMS": "RMS"}
_DETECTOR_ORDER = {"AV": 0, "QP": 1, "PK": 2, "CAV": 3, "CRMS": 4, "RMS": 5}

# Nomes de norma legiveis no combo (o arquivo continua com o nome tecnico).
_METHOD_LABELS = {
    "cispr15_mains_terminals": "Conduzida · terminais de alimentação",
    "cispr15_mains_terminals_sem_eletrodos": "Conduzida · alimentação (lâmpadas sem eletrodos)",
    "cispr15_load_terminals": "Conduzida · terminais de carga",
    "cispr15_control_terminals": "Conduzida · terminais de comando",
    "cispr15_loop_antenna": "Antena loop · campo magnético",
    "cispr15_loop_antenna_sem_eletrodos": "Antena loop · lâmpadas sem eletrodos",
    "cispr15_radiated_30_300": "Irradiada · 30–300 MHz",
}


def _br(x: float | None, decimals: int) -> str:
    """Numero no formato brasileiro (virgula decimal)."""
    if x is None:
        return "-"
    return f"{x:.{decimals}f}".replace(".", ",")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(theme.WINDOW_TITLE)
        self.setWindowIcon(theme.app_icon())
        self.resize(1400, 900)
        # Minimo generoso o bastante para caber numa tela pequena e
        # ainda permitir encolher a janela: o conteudo que nao couber
        # passa a rolar, em vez de travar o redimensionamento.
        self.setMinimumSize(880, 520)

        self.trace: Trace | None = None
        self.traces: dict[str, Trace] = {}   # um trace por detector
        self.method: StandardMethod | None = None
        self.method_path: Path | None = None
        self.results: list[EvaluationResult] = []
        self.incerteza = None
        self.peaks: list[PeakResult] = []
        # resultado da medicao final (picos remedidos em QP/AV no receiver);
        # quando existe, manda nos valores da tabela e do veredito
        self.medicao_final: MedicaoFinal | None = None
        self.plot_theme = "dark"     # grafico da TELA; o do PDF e sempre claro
        self.cable_corr = CorrectionTable.flat("Cabo (manual)", 0.0)
        self.extra_corr = CorrectionTable.flat("LISN/Antena (manual)", 0.0)

        # ---------------- moldura: cabecalho / abas / rodape ----------------
        shell = QWidget()
        shell_l = QVBoxLayout(shell)
        shell_l.setContentsMargins(0, 0, 0, 0)
        shell_l.setSpacing(0)

        self.header = AppHeader()
        shell_l.addWidget(self.header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setDocumentMode(True)
        tabs_wrap = QWidget()
        tabs_wrap_l = QVBoxLayout(tabs_wrap)
        tabs_wrap_l.setContentsMargins(14, 8, 14, 8)
        tabs_wrap_l.addWidget(self.tabs)
        shell_l.addWidget(tabs_wrap, 1)

        self.footer = AppFooter()
        shell_l.addWidget(self.footer)
        self.setCentralWidget(shell)

        # =============== ABA 1: analise / relatorio ===============
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        root.addWidget(splitter)

        # ---- coluna esquerda: controles, dentro de area rolavel ----
        side_host = QWidget()
        left = QVBoxLayout(side_host)
        left.setContentsMargins(2, 2, 10, 8)
        left.setSpacing(12)

        # a area rolavel e criada no fim do __init__, quando todos os
        # controles ja existem (o filtro da roda precisa varrer a arvore)
        self._side_host = side_host
        sidebar = area_rolavel(side_host, largura_min=370, largura_max=560)
        self.sidebar = sidebar
        splitter.addWidget(sidebar)

        # Cabecalho da coluna, com a seta de recolher. O botao do
        # cabecalho do grafico faz o mesmo, mas quem quer esconder a
        # coluna procura o controle NA COLUNA, nao do outro lado da tela.
        side_top = QHBoxLayout()
        side_top.setContentsMargins(4, 0, 0, 0)
        side_top.setSpacing(6)
        titulo_lateral = QLabel("CONTROLES")
        titulo_lateral.setObjectName("cardTitle")
        side_top.addWidget(titulo_lateral)
        side_top.addStretch(1)
        self.painel_hide_btn = QPushButton("◂")
        self.painel_hide_btn.setObjectName("compact")
        self.painel_hide_btn.setFixedWidth(30)
        self.painel_hide_btn.setToolTip("Ocultar esta coluna (F9)")
        self.painel_hide_btn.clicked.connect(
            lambda: self.painel_btn.setChecked(True))
        side_top.addWidget(self.painel_hide_btn)
        left.addLayout(side_top)

        method_box = QGroupBox("Método de ensaio")
        mbox_l = QVBoxLayout(method_box)
        mbox_l.setSpacing(7)
        self.method_combo = self._elastico(QComboBox())
        self._fill_method_combo()
        linha_metodo = QHBoxLayout()
        linha_metodo.setSpacing(8)
        self.method_tile = Ladrilho("C", "teal", 30)
        linha_metodo.addWidget(self.method_tile)
        linha_metodo.addWidget(self.method_combo, 1)
        mbox_l.addLayout(linha_metodo)
        self.method_info = QLabel("—")
        self.method_info.setWordWrap(True)
        self.method_info.setStyleSheet(theme.CSS_DIM)
        mbox_l.addWidget(self.method_info)
        mrow = QHBoxLayout()
        mrow.setSpacing(7)
        edit_btn = QPushButton("Editar limites")
        edit_btn.clicked.connect(self._edit_limits)
        mrow.addWidget(edit_btn)
        manage_std_btn = QPushButton("Gerenciar normas")
        manage_std_btn.clicked.connect(self._manage_standards)
        mrow.addWidget(manage_std_btn)
        mbox_l.addLayout(mrow)
        left.addWidget(method_box)

        file_box = QGroupBox("Dados medidos")
        fbox_l = QVBoxLayout(file_box)
        fbox_l.setSpacing(7)
        load_btn = QPushButton("Importar trace…")
        load_btn.setToolTip("Importa um arquivo de trace (CSV ou ASCII exportado do R&S).")
        load_btn.clicked.connect(self._load_file)
        fbox_l.addWidget(load_btn)
        frow = QHBoxLayout()
        frow.setSpacing(7)
        sample_btn = QPushButton("Exemplo sintético")
        sample_btn.clicked.connect(self._load_sample)
        frow.addWidget(sample_btn)
        clear_btn = QPushButton("Limpar")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(self._clear_traces)
        frow.addWidget(clear_btn)
        fbox_l.addLayout(frow)
        hint = QLabel("Um arquivo por detector (Average, Quasi-Peak, Peak) — "
                       "é assim que o RadiMation exporta.")
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.CSS_DIM)
        fbox_l.addWidget(hint)
        self.det_badges = QHBoxLayout()
        self.det_badges.setSpacing(5)
        self.det_badges.setContentsMargins(0, 2, 0, 2)
        self.det_badges.addStretch(1)
        fbox_l.addLayout(self.det_badges)
        self.file_label = QLabel("Nenhum trace carregado")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet(theme.CSS_MUTED)
        fbox_l.addWidget(self.file_label)
        left.addWidget(file_box)

        corr_box = QGroupBox("Correções (somadas à leitura)")
        corr_l = QFormLayout(corr_box)
        corr_l.setSpacing(8)
        corr_l.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        corr_l.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.cable_combo = self._elastico(QComboBox())
        self.cable_combo.currentIndexChanged.connect(self._on_corr_changed)
        corr_l.addRow("Perda de cabo", self.cable_combo)
        self.cable_spin = QDoubleSpinBox()
        self.cable_spin.setRange(-50, 50)
        self.cable_spin.setSingleStep(0.1)
        self.cable_spin.setSuffix(" dB")
        self.cable_spin.valueChanged.connect(self._on_corr_changed)
        corr_l.addRow("valor manual", self.cable_spin)
        self.extra_combo = self._elastico(QComboBox())
        self.extra_combo.currentIndexChanged.connect(self._on_corr_changed)
        corr_l.addRow("Fator LISN/antena", self.extra_combo)
        self.extra_spin = QDoubleSpinBox()
        self.extra_spin.setRange(-50, 50)
        self.extra_spin.setSingleStep(0.1)
        self.extra_spin.setSuffix(" dB")
        self.extra_spin.valueChanged.connect(self._on_corr_changed)
        corr_l.addRow("valor manual", self.extra_spin)
        manage_corr_btn = QPushButton("Gerenciar tabelas…")
        manage_corr_btn.setToolTip("Criar, editar e excluir tabelas de correção.")
        manage_corr_btn.clicked.connect(self._manage_corrections)
        corr_l.addRow(manage_corr_btn)
        left.addWidget(corr_box)
        self._refresh_correction_combos()

        # ---- cadeia de medicao (equipamentos com certificado) ----
        chain_box = QGroupBox("Cadeia de medição (certificados)")
        chain_l = QVBoxLayout(chain_box)
        chain_l.setSpacing(7)
        legenda = QLabel("Equipamentos usados neste ensaio:")
        legenda.setWordWrap(True)
        legenda.setStyleSheet(theme.CSS_DIM)
        chain_l.addWidget(legenda)
        self.chain_list = QListWidget()
        self.chain_list.setMinimumHeight(96)
        self.chain_list.setMaximumHeight(150)
        self.chain_list.itemChanged.connect(self._on_chain_changed)
        chain_l.addWidget(self.chain_list)
        self.chain_info = QLabel("—")
        self.chain_info.setWordWrap(True)
        self.chain_info.setStyleSheet(theme.CSS_MUTED)
        chain_l.addWidget(self.chain_info)
        left.addWidget(chain_box)
        self._refresh_chain_list()

        # ---- regra de decisao (ISO/IEC 17025 item 7.8.6) ----
        rule_box = QGroupBox("Regra de decisão")
        rule_l = QVBoxLayout(rule_box)
        rule_l.setSpacing(8)
        self.rule_combo = self._elastico(QComboBox())
        for chave, desc in REGRAS.items():
            self.rule_combo.addItem(desc, chave)
        self.rule_combo.currentIndexChanged.connect(self._on_rule_changed)
        rule_l.addWidget(self.rule_combo)
        self.rule41_chk = QCheckBox("Atalho do item 4.1 (QP cobre média)")
        self.rule41_chk.setChecked(True)
        self.rule41_chk.setToolTip(
            "CISPR 15 item 4.1: medindo em quase-pico, se o nível já atende o limite de\n"
            "média, ambos os limites estão atendidos e não precisa medir em média.\n"
            "Se NÃO atende, nada se conclui sobre a média (o nível de média real é menor\n"
            "ou igual ao de QP) — o resultado fica INDETERMINADO, não reprovado.")
        self.rule41_chk.stateChanged.connect(lambda _: self._refresh_plot())
        rule_l.addWidget(self.rule41_chk)
        unc_btn = QPushButton("Editar incertezas…")
        unc_btn.setToolTip("Faixas de incerteza (U, k) usadas pela regra de decisão desta norma.")
        unc_btn.clicked.connect(self._edit_uncertainty)
        rule_l.addWidget(unc_btn)
        self.rule_info = QLabel("—")
        self.rule_info.setWordWrap(True)
        self.rule_info.setStyleSheet(theme.CSS_MUTED)
        rule_l.addWidget(self.rule_info)
        left.addWidget(rule_box)

        eval_btn = QPushButton("Avaliar contra o limite")
        eval_btn.setObjectName("primary")
        eval_btn.setMinimumHeight(38)
        eval_btn.clicked.connect(self._evaluate)
        left.addWidget(eval_btn)

        report_box = QGroupBox("Relatório")
        rbox_l = QFormLayout(report_box)
        rbox_l.setSpacing(8)
        rbox_l.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        rbox_l.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.eut_name_edit = QLineEdit()
        self.eut_name_edit.setPlaceholderText("ex.: Luminária LED 20 W")
        rbox_l.addRow("EUT", self.eut_name_edit)
        self.operator_edit = QLineEdit()
        self.operator_edit.setPlaceholderText("quem executou o ensaio")
        rbox_l.addRow("Operador", self.operator_edit)
        self.receiver_edit = QLineEdit("R&S ESR / ESPI / ESRP")
        rbox_l.addRow("Receiver", self.receiver_edit)
        self.lisn_edit = QLineEdit("R&S ENV216")
        rbox_l.addRow("LISN/Antena", self.lisn_edit)
        pdf_btn = QPushButton("Gerar PDF…")
        pdf_btn.setToolTip("Gera o relatório PDF padronizado laboratório com gráfico e tabelas.")
        pdf_btn.setMinimumHeight(34)
        pdf_btn.clicked.connect(self._export_pdf)
        rbox_l.addRow(pdf_btn)
        left.addWidget(report_box)

        left.addStretch(1)

        # ---- coluna direita: grafico + veredito + tabelas ----
        right_host = QWidget()
        right = QVBoxLayout(right_host)
        right.setContentsMargins(10, 2, 2, 8)
        right.setSpacing(12)
        splitter.addWidget(right_host)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 1000])

        # cartao do grafico, com barra de titulo propria
        plot_frame = QFrame()
        plot_frame.setObjectName("plotFrame")
        pf_l = QVBoxLayout(plot_frame)
        pf_l.setContentsMargins(12, 9, 12, 12)
        pf_l.setSpacing(8)
        pf_top = QHBoxLayout()
        pf_top.setSpacing(6)
        # recolher a coluna de controles deixa o espectro sozinho e
        # centralizado -- e o modo de olhar o traco, nao de configurar
        self.painel_btn = QPushButton("◂  Ocultar painel")
        self.painel_btn.setObjectName("toggle")
        self.painel_btn.setCheckable(True)
        self.painel_btn.setShortcut(QKeySequence("F9"))
        self.painel_btn.setToolTip(
            "Recolhe a coluna de controles à esquerda  (F9).\n"
            "Só o espectro fica na tela, ocupando a largura toda.")
        self.painel_btn.toggled.connect(self._on_painel_toggled)
        pf_top.addWidget(self.painel_btn)
        self.plot_title = QLabel("ESPECTRO")
        self.plot_title.setObjectName("cardTitle")
        pf_top.addWidget(self.plot_title)
        pf_top.addStretch(1)
        self.theme_btn = QPushButton("Fundo claro")
        self.theme_btn.setObjectName("ghost")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setToolTip("Alterna o fundo do gráfico NA TELA.\n"
                                   "O gráfico do PDF é sempre em fundo branco.")
        self.theme_btn.toggled.connect(self._on_plot_theme_toggled)
        pf_top.addWidget(self.theme_btn)
        png_btn = QPushButton("Exportar PNG")
        png_btn.setObjectName("ghost")
        png_btn.clicked.connect(self._export_png)
        pf_top.addWidget(png_btn)
        self.tabela_btn = QPushButton("Tabela  ▸")
        self.tabela_btn.setObjectName("toggle")
        self.tabela_btn.setCheckable(True)
        self.tabela_btn.setShortcut(QKeySequence("F10"))
        self.tabela_btn.setToolTip(
            "Abre a tabela de picos ao lado do gráfico  (F10).\n"
            "Fechada, o gráfico ocupa o painel inteiro.")
        self.tabela_btn.toggled.connect(self._on_tabela_toggled)
        pf_top.addWidget(self.tabela_btn)
        pf_l.addLayout(pf_top)
        self.canvas = PlotCanvas(self)
        pf_l.addWidget(self.canvas, 1)
        self.verdict_bar = VerdictBar()

        # Resultados: a tabela "Picos Detectados" (mesmas colunas do PDF) e o
        # resumo de veredito por detector, em abas para caber na tela.
        self.result_tabs = QTabWidget()
        self.result_tabs.setDocumentMode(True)
        self.peak_table = self._make_table()
        self.result_tabs.addTab(self.peak_table, "Picos detectados")
        self.result_table = self._make_table()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(
            ["Detector", "Pior margem (dB)", "Frequência crítica", "Veredito"])
        self.result_tabs.addTab(self.result_table, "Veredito por detector")

        self.painel_tabela = QFrame()
        self.painel_tabela.setObjectName("card")
        pt_l = QVBoxLayout(self.painel_tabela)
        pt_l.setContentsMargins(12, 9, 12, 12)
        pt_l.setSpacing(8)
        pt_l.addWidget(self.result_tabs, 1)
        self.painel_tabela.setMinimumWidth(420)
        self.painel_tabela.hide()          # fechado por padrao: grafico inteiro

        # O grafico mantem a proporcao do laudo (1,95 : 1). Empilhado com a
        # tabela embaixo ele sobrava largura e faltava altura, virando um
        # filete. Lado a lado o grafico usa a altura toda do painel -- e com
        # a proporcao travada, mais altura significa tambem mais largura.
        # Por isso a tabela abre AO LADO, e nao embaixo.
        self.hsplit_result = QSplitter(Qt.Horizontal)
        self.hsplit_result.setChildrenCollapsible(False)
        self.hsplit_result.setHandleWidth(8)
        self.hsplit_result.addWidget(plot_frame)
        self.hsplit_result.addWidget(self.painel_tabela)
        self.hsplit_result.setStretchFactor(0, 3)
        self.hsplit_result.setStretchFactor(1, 2)
        right.addWidget(self.hsplit_result, 1)
        right.addWidget(self.verdict_bar)

        # ---- as tres telas de emissao ficam sob a secao CISPR 15 ----
        self.cispr_tabs = QTabWidget()
        self.cispr_tabs.setDocumentMode(True)
        self.cispr_tabs.addTab(central, "Análise")

        self.receiver_tab = ReceiverTab(self)
        self.receiver_tab.trace_acquired.connect(self._on_trace_acquired)
        self.receiver_tab.final_measurement_done.connect(self._on_final_measurement)
        self.receiver_tab.provedor_de_picos = self._picos_para_medicao_final
        self.cispr_tabs.addTab(self.receiver_tab, "Receiver / GPIB")

        self.equip_tab = EquipamentosTab(self)
        self.equip_tab.catalogo_mudou.connect(self._refresh_chain_list)
        self.cispr_tabs.addTab(self.equip_tab, "Equipamentos")

        self.tabs.addTab(self.cispr_tabs, "CISPR 15  ·  Emissão")

        # ---- secao EMC: ensaios de imunidade (IEC 61000-4-4/4-5/4-11) ----
        # Carregada aqui e nao no topo do arquivo: se o pacote emc/ nao
        # estiver presente, o HALO continua abrindo so com a parte de
        # emissao em vez de morrer na importacao.
        self.emc_section = None
        try:
            from emc.core.db import init_db
            from gui.emc_section import EmcSection
            init_db()
            self.emc_section = EmcSection(self)
            self.tabs.addTab(self.emc_section, "EMC  ·  Imunidade")
        except Exception as e:
            aviso = QLabel(
                "A seção EMC (imunidade) não pôde ser carregada:\n\n"
                f"{type(e).__name__}: {e}\n\n"
                "A parte de emissão CISPR 15 continua funcionando normalmente.")
            aviso.setWordWrap(True)
            aviso.setAlignment(Qt.AlignCenter)
            aviso.setStyleSheet(theme.CSS_FAIL)
            self.tabs.addTab(aviso, "EMC  ·  Imunidade")

        # ---- Dispositivos: transversal, serve emissao e imunidade ----
        # E a aba Devices do RadiMation. Nao fica dentro de nenhuma das
        # duas secoes de ensaio porque o mesmo cabo, o mesmo atenuador e o
        # mesmo certificado servem aos dois lados.
        self.dispositivos_tab = DispositivosTab(self)
        self.dispositivos_tab.catalogo_mudou.connect(self._refresh_chain_list)
        self.tabs.addTab(self.dispositivos_tab, "Dispositivos")

        self._load_method()
        self.method_combo.currentIndexChanged.connect(self._load_method)

        self._montar_menus()

        # roda do mouse: rola a tela em vez de trocar o valor do campo
        # sob o cursor (vale para todas as abas)
        desarmar_roda(self)

    # ---------------- barra de menus ----------------
    def _montar_menus(self):
        """Barra de menus no estilo dos programas de bancada: tudo o que a
        interface faz também está aqui, agrupado por assunto e subdividido.

        Vale a repetição com os botões das telas: num programa de ensaio o
        operador aprende o caminho do menu e passa a usá-lo sem procurar o
        botão, e quem chega novo descobre o que existe percorrendo os menus
        em vez de clicar em cada aba."""
        barra = self.menuBar()

        def acao(menu, texto, slot, atalho: str = "", dica: str = ""):
            a = menu.addAction(texto)
            if atalho:
                a.setShortcut(QKeySequence(atalho))
            if dica:
                a.setStatusTip(dica)
            a.triggered.connect(slot)
            return a

        def ir(secao: int, aba: int = 0):
            def _f():
                self.tabs.setCurrentIndex(secao)
                if secao == 0:
                    self.cispr_tabs.setCurrentIndex(aba)
            return _f

        # ---------------------------------------------------------- Arquivo
        m = barra.addMenu("&Arquivo")
        sub = m.addMenu("Importar trace")
        acao(sub, "De arquivo (CSV / ASCII R&&S)…", self._load_file, "Ctrl+O")
        acao(sub, "Exemplo sintético da norma", self._load_sample)
        m.addSeparator()
        sub = m.addMenu("Exportar")
        acao(sub, "Gráfico como PNG…", self._export_png)
        acao(sub, "Relatório em PDF…", self._export_pdf, "Ctrl+P")
        m.addSeparator()
        acao(m, "Limpar traces carregados", self._clear_traces)
        m.addSeparator()
        acao(m, "Sair", self.close, "Ctrl+Q")

        # ------------------------------------------------------------ Ensaio
        m = barra.addMenu("&Ensaio")
        sub = m.addMenu("Emissão — CISPR 15")
        acao(sub, "Análise do espectro", ir(0, 0), "Ctrl+1")
        acao(sub, "Receiver / GPIB", ir(0, 1), "Ctrl+2")
        acao(sub, "Equipamentos e certificados", ir(0, 2), "Ctrl+3")
        sub = m.addMenu("Imunidade — EMC")
        if self.emc_section is not None:
            for nome in self.emc_section.ABAS:
                acao(sub, nome,
                      (lambda n=nome: (self.tabs.setCurrentIndex(1),
                                        self.emc_section.ir_para(n))))
        else:
            sub.addAction("(seção não carregada)").setEnabled(False)
        m.addSeparator()
        acao(m, "Avaliar contra o limite", self._evaluate, "F5")
        acao(m, "Medição final nos picos…", self._menu_medicao_final, "F6")

        # ------------------------------------------------------------- Norma
        m = barra.addMenu("&Norma")
        self._menu_normas = m.addMenu("Selecionar método")
        self._preencher_menu_normas()
        m.addSeparator()
        acao(m, "Editar limites da norma atual…", self._edit_limits)
        acao(m, "Gerenciar normas (novo / duplicar / excluir)…", self._manage_standards)
        m.addSeparator()
        acao(m, "Incertezas e regra de decisão…", self._edit_uncertainty)

        # ---------------------------------------------------------- Correções
        m = barra.addMenu("&Dispositivos")
        acao(m, "Cadastro de dispositivos", ir(2), "Ctrl+D")
        sub = m.addMenu("Ir para o grupo")
        for _g in GRUPOS:
            acao(sub, _g, (lambda g=_g: self._ir_grupo_dispositivo(g)))
        m.addSeparator()
        acao(m, "Tabelas de correção…", self._manage_corrections)
        acao(m, "Equipamentos (cadastro antigo)…", ir(0, 2))

        # ----------------------------------------------------------- Exibir
        m = barra.addMenu("E&xibir")
        sub = m.addMenu("Painéis")
        a = sub.addAction("Coluna de controles")
        a.setCheckable(True); a.setChecked(True); a.setShortcut(QKeySequence("F9"))
        a.toggled.connect(lambda on: self.painel_btn.setChecked(not on))
        a = sub.addAction("Tabela de picos ao lado")
        a.setCheckable(True); a.setShortcut(QKeySequence("F10"))
        a.toggled.connect(self.tabela_btn.setChecked)
        sub = m.addMenu("Gráfico")
        a = sub.addAction("Fundo claro (como no laudo)")
        a.setCheckable(True)
        a.toggled.connect(self.theme_btn.setChecked)
        m.addSeparator()
        acao(m, "Aparência e cores…", self._abrir_paleta)

        # ------------------------------------------------------------- Ajuda
        m = barra.addMenu("A&juda")
        acao(m, "Avisos técnicos em aberto…", self._mostrar_avisos)
        acao(m, f"Sobre o {theme.APP_NAME}…", self._sobre)

    def _preencher_menu_normas(self):
        self._menu_normas.clear()
        for i in range(self.method_combo.count()):
            rotulo = self.method_combo.itemText(i)
            a = self._menu_normas.addAction(rotulo)
            a.setCheckable(True)
            a.setChecked(i == self.method_combo.currentIndex())
            a.triggered.connect(lambda _=False, k=i: self.method_combo.setCurrentIndex(k))

    def _ir_grupo_dispositivo(self, grupo: str):
        """Abre Dispositivos filtrando pelo grupo escolhido."""
        self.tabs.setCurrentWidget(self.dispositivos_tab)
        self.dispositivos_tab.filtro.clear()
        arv = self.dispositivos_tab.arvore
        for i in range(arv.topLevelItemCount()):
            it = arv.topLevelItem(i)
            it.setExpanded(it.text(0) == grupo.upper())
            if it.text(0) == grupo.upper():
                arv.scrollToItem(it)

    def _menu_medicao_final(self):
        """Leva para a sub-aba de medição final, já na seção certa."""
        self.tabs.setCurrentIndex(0)
        self.cispr_tabs.setCurrentIndex(1)
        for i in range(self.receiver_tab.tabs.count()):
            if "final" in self.receiver_tab.tabs.tabText(i).lower():
                self.receiver_tab.tabs.setCurrentIndex(i)
                break

    def _abrir_paleta(self):
        from gui.paleta_dialog import PaletaDialog
        PaletaDialog(self).exec()

    def _mostrar_avisos(self):
        QMessageBox.information(
            self, "Avisos técnicos em aberto",
            "Pontos que dependem de decisão do laboratório ou de validação:\n\n"
            "• Tempo de medição em quase-pico: a configuração usa 50 ms, contra "
            "constantes de descarga de 160–550 ms da CISPR 16-1-1. O erro tende "
            "a APROVAR.\n\n"
            "• Escopo 2014: a CISPR 15:2018 aperta 200–300 MHz em até 10 dB.\n\n"
            "• Antena loop: a norma expressa o limite em dB(µA/m); a tabela "
            "transcrita está em dBµA. Confirmar antes de usar.\n\n"
            "• Comandos SCPI do catálogo NÃO foram validados contra hardware.\n\n"
            "• Cláusula 5 (cliques) não implementada.\n\n"
            "Detalhes em instrucoes/.")

    def _sobre(self):
        QMessageBox.about(
            self, f"Sobre o {theme.APP_NAME}",
            f"<b>{theme.APP_NAME}</b> {theme.APP_VERSION}<br>"
            f"{theme.APP_TAGLINE}<br><br>"
            "Emissão conforme ABNT NBR IEC/CISPR 15:2014 e imunidade "
            "IEC 61000-4-4 / 4-5 / 4-11.<br><br>"
            "<i>Os comandos SCPI pré-setados não foram validados contra "
            "hardware real. Confira no manual do seu instrumento antes de "
            "usar em ensaio acreditado.</i>")

    # ---------------- helpers de aparencia ----------------
    @staticmethod
    def _elastico(combo: QComboBox) -> QComboBox:
        """Impede que um item longo dentro do combo estique a coluna
        lateral inteira -- o texto e elidido em vez de empurrar o layout."""
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return combo

    @staticmethod
    def _ajustar_colunas(t: QTableWidget):
        """Larguras de coluna: primeiro o que o conteudo pede; se sobrar
        espaco, distribui o resto para a tabela ocupar a largura toda. Se
        NAO couber, mantem o conteudo legivel e deixa rolar na horizontal
        -- e melhor rolar do que ler um cabecalho cortado pela metade."""
        header = t.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        t.resizeColumnsToContents()
        preciso = sum(header.sectionSize(i) for i in range(t.columnCount()))
        disponivel = t.viewport().width()
        if t.columnCount() and preciso <= disponivel:
            header.setSectionResizeMode(QHeaderView.Stretch)
        else:
            header.setSectionResizeMode(QHeaderView.Interactive)

    def _make_table(self) -> QTableWidget:
        t = FitTable()
        t.set_ajuste(self._ajustar_colunas)
        t.setAlternatingRowColors(True)
        t.setShowGrid(True)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(26)
        t.horizontalHeader().setMinimumHeight(56)
        t.setMinimumHeight(90)
        t.horizontalHeader().setHighlightSections(False)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        return t

    def _fill_method_combo(self):
        self._methods = list_available_methods()
        for p in self._methods:
            self.method_combo.addItem(_METHOD_LABELS.get(p.stem, p.stem), str(p))

    def _on_plot_theme_toggled(self, claro: bool):
        self.plot_theme = "light" if claro else "dark"
        self.theme_btn.setText("Fundo escuro" if claro else "Fundo claro")
        self._refresh_plot()

    def _on_painel_toggled(self, recolhido: bool):
        """Esconde/mostra a coluna de controles da esquerda."""
        self.sidebar.setVisible(not recolhido)
        self.painel_btn.setText("▸  Mostrar painel" if recolhido
                                 else "◂  Ocultar painel")

    def _on_tabela_toggled(self, aberta: bool):
        """Abre/fecha o painel da tabela ao lado do grafico."""
        self.tabela_btn.setText("Tabela  ◂" if aberta else "Tabela  ▸")
        self.painel_tabela.setVisible(aberta)
        if aberta:
            total = max(self.hsplit_result.width(), 900)
            self.hsplit_result.setSizes([int(total * 0.58), int(total * 0.42)])
        self._atualizar_contador_tabela()

    def _atualizar_contador_tabela(self):
        """Mostra a contagem de picos no proprio botao, para o operador saber
        que ha resultado ali mesmo com o painel fechado."""
        n = len(self.peaks)
        # isVisible() e falso enquanto a janela nao foi mostrada; o
        # estado do botao e a fonte confiavel de "painel aberto"
        seta = "◂" if self.tabela_btn.isChecked() else "▸"
        self.tabela_btn.setText(f"Tabela ({n})  {seta}" if n else f"Tabela  {seta}")

    def _export_png(self):
        if self.method is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar gráfico", "grafico_cispr15.png",
                                               "PNG (*.png)")
        if not path:
            return
        self.canvas.figure.savefig(path, dpi=200,
                                    facecolor=self.canvas.figure.get_facecolor())
        self.footer.set_mensagem(f"Gráfico salvo em {path}", theme.OK)

    # ---------------- metodo / norma ----------------
    def _load_method(self):
        idx = self.method_combo.currentIndex()
        if idx < 0:
            return
        path = Path(self.method_combo.itemData(idx))
        self.method = load_method(path)
        self.method_path = path
        self._update_method_info()
        self._load_uncertainty()
        self._refresh_plot()

    def _update_method_info(self):
        if self.method is None:
            self.method_info.setText("—")
            return
        f0, f1 = self.method.freq_range_hz
        dets = ", ".join(sorted({ll.detector for ll in self.method.limit_lines}))
        nao_verif = [ll.detector for ll in self.method.limit_lines
                     if not ll.is_fully_verified()]
        texto = (f"{self.method.id}\n"
                 f"{f0/1e3:g} kHz – {f1/1e6:g} MHz · detectores: {dets or '—'}")
        if nao_verif:
            texto += f"\n⚠ limite não verificado: {', '.join(nao_verif)}"
            self.method_info.setStyleSheet(theme.CSS_WARN)
        else:
            self.method_info.setStyleSheet(theme.CSS_DIM)
        self.method_info.setText(texto)
        self.header.chip_norma.set_valor(
            _METHOD_LABELS.get(self.method.id, self.method.id))
        letra, cor = self._TIPO_LADRILHO.get(self.method.id, ("?", "cinza"))
        self.method_tile.setText(letra)
        self.method_tile.set_cor(cor)

    def _edit_limits(self):
        if self.method is None:
            return
        dlg = LimitEditorDialog(self.method, self.method_path, self)
        if dlg.exec():
            self.method = load_method(self.method_path)
            self._update_method_info()
            self._refresh_plot()

    # ---------------- incerteza / regra de decisao ----------------
    def _load_uncertainty(self):
        """Carrega a configuracao de incerteza da norma atual."""
        if self.method is None:
            self.incerteza = None
            return
        self.incerteza = carregar_incerteza(self.method.id)
        self.rule_combo.blockSignals(True)
        idx = self.rule_combo.findData(self.incerteza.regra)
        self.rule_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.rule_combo.blockSignals(False)
        self._update_rule_info()

    def _update_rule_info(self):
        if self.incerteza is None:
            self.rule_info.setText("—")
            return
        faixas = self.incerteza.faixas
        if faixas:
            us = ", ".join(f"{f.u_lab_db:g} dB" for f in faixas)
            texto = f"{len(faixas)} faixa(s) · U = {us} (k={faixas[0].fator_k:g})"
        else:
            texto = "Sem faixas de incerteza cadastradas."
        avisos = self.incerteza.avisos()
        if avisos and self.incerteza.regra != "risco_compartilhado":
            texto += "\n⚠ " + avisos[0]
            self.rule_info.setStyleSheet(theme.CSS_WARN)
        else:
            self.rule_info.setStyleSheet(theme.CSS_MUTED)
        self.rule_info.setText(texto)

    def _on_rule_changed(self):
        if self.incerteza is None:
            return
        self.incerteza.regra = self.rule_combo.currentData()
        salvar_incerteza(self.incerteza)
        self._update_rule_info()
        self._refresh_plot()

    def _edit_uncertainty(self):
        if self.method is None:
            return
        if self.incerteza is None:
            self._load_uncertainty()
        dlg = IncertezaDialog(self.incerteza, self)
        if dlg.exec():
            self._load_uncertainty()
            self._refresh_plot()

    def _manage_standards(self):
        dlg = StandardsManagerDialog(self)
        dlg.exec()
        if dlg.changed:
            current_path = self.method_path
            self.method_combo.blockSignals(True)
            self.method_combo.clear()
            self._fill_method_combo()
            self.method_combo.blockSignals(False)
            idx = self.method_combo.findData(str(current_path)) if current_path else -1
            self.method_combo.setCurrentIndex(idx if idx >= 0 else 0 if self._methods else -1)
            self._load_method()

    # ---------------- dados ----------------
    # Preferencia para escolher o trace "principal" (o que localiza os picos):
    # o prescan e feito em detector de pico, entao PK vem primeiro.
    _PRIMARIO = ("PK", "QP", "AV", "CAV", "RMS", "CRMS")

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar trace", "",
                                               "Trace files (*.csv *.txt *.dat *.asc);;Todos (*.*)")
        if not path:
            return
        try:
            trace = load_trace(path)
        except Exception as e:
            QMessageBox.warning(self, "Erro ao importar", str(e))
            return

        # Um arquivo = um detector. O RadiMation exporta um trace por
        # detector (Average, Quasi-Peak, Peak); importe um de cada vez.
        opcoes = [d for d in self._PRIMARIO]
        atual = (trace.detector or "").upper()
        inicial = opcoes.index(atual) if atual in opcoes else 0
        det, ok = QInputDialog.getItem(
            self, "Detector deste arquivo",
            f"{Path(path).name}\n\nCom que detector este trace foi medido?",
            opcoes, inicial, False)
        if not ok:
            return
        trace.detector = det
        self.traces[det] = trace
        self._set_primary_trace()
        self._update_file_label()
        self.footer.set_mensagem(f"Trace {det} importado de {Path(path).name}", theme.OK)
        self._refresh_plot()

    def _clear_traces(self):
        self.traces = {}
        self.trace = None
        self.medicao_final = None   # pertence ao ensaio que acabou de sair
        self._update_file_label()
        self.footer.set_mensagem("Traces removidos.")
        self._refresh_plot()

    def _set_primary_trace(self):
        """O trace principal e o usado para localizar os picos."""
        for det in self._PRIMARIO:
            if det in self.traces:
                self.trace = self.traces[det]
                return
        self.trace = next(iter(self.traces.values()), None)

    def _update_file_label(self):
        if not self.traces:
            self.file_label.setText("Nenhum trace carregado")
            self.file_label.setStyleSheet(theme.CSS_DIM)
            self.header.chip_traces.set_valor("nenhum", theme.TEXT_DIM)
            return
        linhas = []
        for det in sorted(self.traces, key=lambda d: self._PRIMARIO.index(d)
                          if d in self._PRIMARIO else 99):
            t = self.traces[det]
            marca = " ◂ principal" if t is self.trace else ""
            linhas.append(f"<b>{det}</b>{marca} — {len(t.freq_hz)} pts · "
                          f"{t.freq_hz.min()/1e3:.1f} kHz–{t.freq_hz.max()/1e6:.2f} MHz · {t.unit}")
        self.file_label.setText("<br>".join(linhas))
        self.file_label.setStyleSheet(theme.CSS_MUTED)
        self.header.chip_traces.set_valor(
            " · ".join(sorted(self.traces, key=lambda d: self._PRIMARIO.index(d)
                              if d in self._PRIMARIO else 99)), theme.TEXT)
        self._atualizar_badges_detector()

    _TIPO_LADRILHO = {
        "cispr15_mains_terminals": ("C", "teal"),
        "cispr15_mains_terminals_sem_eletrodos": ("C", "azul"),
        "cispr15_load_terminals": ("L", "verde"),
        "cispr15_control_terminals": ("K", "ambar"),
        "cispr15_loop_antenna": ("H", "roxo"),
        "cispr15_loop_antenna_sem_eletrodos": ("H", "rosa"),
        "cispr15_radiated_30_300": ("R", "vermelho"),
    }

    def _atualizar_badges_detector(self):
        """Uma etiqueta colorida por detector carregado. Cor fixa por
        detector, a mesma da tabela e da legenda do grafico."""
        # Remove SO os widgets. Tirar o item esticavel junto faria as
        # badges se esticarem para preencher a caixa -- uma delas
        # cobria o cartao inteiro com a propria cor de fundo.
        for i in reversed(range(self.det_badges.count())):
            item = self.det_badges.itemAt(i)
            if item is not None and item.widget() is not None:
                item.widget().setParent(None)
        ordem = [d for d in self._PRIMARIO if d in self.traces]
        for det in ordem:
            b = Badge(det, theme.COR_DETECTOR.get(det, "cinza"))
            t = self.traces[det]
            marca = "  (principal)" if t is self.trace else ""
            b.setToolTip(f"{det}{marca} — {len(t.freq_hz)} pontos, "
                          f"{t.freq_hz.min()/1e3:.1f} kHz a {t.freq_hz.max()/1e6:.2f} MHz")
            self.det_badges.insertWidget(self.det_badges.count() - 1, b, 0, Qt.AlignLeft)
        if self.medicao_final is not None and self.medicao_final.pontos:
            mf = Badge("MED. FINAL", "verde")
            mf.setToolTip(self.medicao_final.resumo())
            self.det_badges.insertWidget(self.det_badges.count() - 1, mf, 0, Qt.AlignLeft)

    def _load_sample(self):
        sample_dir = Path(__file__).parent.parent / "data"
        candidates = {
            "cispr15_mains_terminals": "demo_10_picos_conducted.csv",
            "cispr15_load_terminals": "sample_conducted_trace.csv",
            "cispr15_control_terminals": "sample_conducted_trace.csv",
            "cispr15_loop_antenna": "sample_loop_trace.csv",
            "cispr15_radiated_30_300": "sample_radiated_trace.csv",
        }
        fname = candidates.get(self.method.id if self.method else "", "sample_conducted_trace.csv")
        path = sample_dir / fname
        if not path.exists():
            QMessageBox.warning(self, "Não encontrado", f"Exemplo {path} não existe.")
            return
        trace = load_trace(path)
        det = (trace.detector or "").upper()
        trace.detector = det if det in self._PRIMARIO else "PK"
        self.traces = {trace.detector: trace}
        self._set_primary_trace()
        self._update_file_label()
        self.footer.set_mensagem(f"[exemplo sintético] {path.name}", theme.WARN)
        self._refresh_plot()

    def _refresh_correction_combos(self):
        self._corrections = list_available_corrections()
        for combo, spin in ((self.cable_combo, self.cable_spin), (self.extra_combo, self.extra_spin)):
            current_data = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(MANUAL_CORR_LABEL, None)
            for p in self._corrections:
                combo.addItem(p.stem, str(p))
            idx = combo.findData(current_data) if current_data else -1
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            spin.setEnabled(combo.currentIndex() == 0)
            combo.blockSignals(False)
        self._on_corr_changed()

    def _manage_corrections(self):
        dlg = CorrectionsManagerDialog(self)
        dlg.exec()
        if dlg.changed:
            self._refresh_correction_combos()
            self._refresh_plot()

    def _on_trace_acquired(self, trace: Trace):
        """Recebe um trace medido ao vivo pela aba Receiver e joga na analise."""
        det = (trace.detector or "PK").upper()
        self.traces[det] = trace
        self._set_primary_trace()
        self._update_file_label()
        self.footer.set_mensagem(f"[medido ao vivo] {trace.label} · {len(trace.freq_hz)} pontos",
                                  theme.OK)
        self.tabs.setCurrentIndex(0)
        self._refresh_plot()

    # ---------------- medicao final (picos remedidos no receiver) ----------
    def _picos_para_medicao_final(self, margem_db: float,
                                   max_picos: int) -> list[tuple[float, float]]:
        """Frequencias que a aba Receiver deve remedir, com o nivel do prescan.

        Sao os picos DENTRO DA MARGEM de algum limite -- o critério de
        redução de dados. Não adianta remedir um pico 30 dB abaixo do
        limite: ele já passou, e cada remedição custa segundos de bancada.
        """
        if self.trace is None or self.method is None:
            return []
        trace = self._corrected_trace()
        picos = detect_peaks(trace, self.method,
                              margin_db=margem_db,
                              max_peaks=max_picos,
                              detector_traces=self._corrected_traces(),
                              regra_4_1=self.rule41_chk.isChecked())
        return [(p.freq_hz, p.level) for p in picos]

    def _on_final_measurement(self, resultado: MedicaoFinal):
        """Recebe a medição final e refaz tabela, gráfico e veredito com ela."""
        self.medicao_final = resultado
        avisos = resultado.inconsistencias()
        self.footer.set_mensagem(
            resultado.resumo() + (f"  ⚠ {len(avisos)} inconsistência(s)" if avisos else ""),
            theme.WARN if avisos else theme.OK)
        self.tabs.setCurrentIndex(0)
        self._refresh_plot()
        if avisos:
            QMessageBox.warning(
                self, "Medição final com inconsistência",
                "A medição final devolveu valores fisicamente impossíveis:\n\n"
                + "\n".join(avisos)
                + "\n\nConfira tempo de medição, atenuação e sobrecarga do receiver.")

    def _on_corr_changed(self):
        self.cable_spin.setEnabled(self.cable_combo.currentIndex() == 0)
        self.extra_spin.setEnabled(self.extra_combo.currentIndex() == 0)

        cable_path = self.cable_combo.currentData()
        if cable_path:
            self.cable_corr = load_correction(cable_path)
        else:
            self.cable_corr = CorrectionTable.flat("Cabo (manual)", self.cable_spin.value())

        extra_path = self.extra_combo.currentData()
        if extra_path:
            self.extra_corr = load_correction(extra_path)
        else:
            self.extra_corr = CorrectionTable.flat("LISN/antena (manual)", self.extra_spin.value())

        if getattr(self, "method", None) is not None:
            self._refresh_plot()

    # ---------------- cadeia de medicao (certificados) ----------------
    def _refresh_chain_list(self):
        """Lista os equipamentos cadastrados, marcaveis, preservando a selecao."""
        marcados = self._chain_checked_ids()
        self.chain_list.blockSignals(True)
        self.chain_list.clear()
        for p in listar_equipamentos():
            try:
                eq = carregar_equipamento(p)
            except Exception:
                continue
            if not eq.ativo:
                continue
            cert = eq.certificado()
            rotulo = f"[{eq.tipo}] {eq.rotulo()}"
            if cert is None or not cert.pontos:
                rotulo += "  (sem certificado)"
            elif cert.vencido_em():
                rotulo += "  ⚠ VENCIDO"
            item = QListWidgetItem(rotulo)
            item.setData(Qt.UserRole, str(p))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if str(p) in marcados else Qt.Unchecked)
            if cert is not None and cert.vencido_em():
                item.setForeground(theme.status_color("REPROVADO"))
            self.chain_list.addItem(item)
        self.chain_list.blockSignals(False)
        self._update_chain_info()

    def _chain_checked_ids(self) -> set[str]:
        return {self.chain_list.item(i).data(Qt.UserRole)
                for i in range(self.chain_list.count())
                if self.chain_list.item(i).checkState() == Qt.Checked}

    def _chain_equipments(self) -> list:
        equipamentos = []
        for path in self._chain_checked_ids():
            try:
                equipamentos.append(carregar_equipamento(path))
            except Exception:
                continue
        return equipamentos

    def _on_chain_changed(self):
        self._update_chain_info()
        self._refresh_plot()

    def _update_chain_info(self):
        equipamentos = self._chain_equipments()
        if not equipamentos:
            self.chain_info.setText("Nenhum equipamento selecionado — sem correção por certificado.")
            self.chain_info.setStyleSheet(theme.CSS_DIM)
            return
        if self.trace is not None:
            freq = self.trace.freq_hz
        elif self.method is not None:
            import numpy as np
            freq = np.array(self.method.freq_range_hz, dtype=float)
        else:
            import numpy as np
            freq = np.array([9e3, 30e6])
        r = aplicar_cadeia(freq, equipamentos)
        texto = (f"{len(r.equipamentos)} equipamento(s): correção de "
                 f"{r.correcao_db.min():+.2f} a {r.correcao_db.max():+.2f} dB · "
                 f"incerteza U(k={r.fator_k:g}) até ±{r.incerteza_expandida_db.max():.2f} dB")
        if r.avisos:
            texto += "\n⚠ " + "\n⚠ ".join(r.avisos)
            self.chain_info.setStyleSheet(theme.CSS_FAIL)
        else:
            self.chain_info.setStyleSheet(theme.CSS_MUTED)
        self.chain_info.setText(texto)

    def _apply_corrections(self, trace: Trace | None) -> Trace | None:
        """Aplica ao trace as correcoes manuais/tabela e a cadeia de certificados."""
        if trace is None:
            return None
        t = self.cable_corr.apply(trace)
        t = self.extra_corr.apply(t)

        equipamentos = self._chain_equipments()
        if equipamentos:
            r = aplicar_cadeia(t.freq_hz, equipamentos)
            t = Trace(freq_hz=t.freq_hz.copy(), level=t.level + r.correcao_db,
                      unit=t.unit, detector=t.detector,
                      label=t.label + f" + cadeia ({len(r.equipamentos)} eq.)",
                      source_file=t.source_file, meta=dict(t.meta))
        return t

    def _corrected_trace(self) -> Trace | None:
        return self._apply_corrections(self.trace)

    def _corrected_traces(self) -> dict[str, Trace]:
        """Todos os traces carregados, ja corrigidos, indexados por detector."""
        return {det: self._apply_corrections(t) for det, t in self.traces.items()}

    # ---------------- avaliacao / plot ----------------
    def _refresh_plot(self):
        if self.method is None:
            return
        trace = self._corrected_trace()
        if trace is None:
            import numpy as np
            trace = Trace(freq_hz=np.array(self.method.freq_range_hz, dtype=float),
                           level=np.array([np.nan, np.nan]), unit="dBuV", label="(sem dados)")
            self.results = []
            self.peaks = []
        else:
            regra41 = self.rule41_chk.isChecked()
            outros = self._corrected_traces()
            self.results = evaluate(trace, self.method, incerteza=self.incerteza,
                                     detector_traces=outros, regra_4_1=regra41)
            self.peaks = detect_peaks(trace, self.method, detector_traces=outros,
                                       regra_4_1=regra41,
                                       medicao_final=self.medicao_final)
        fig = build_figure(trace, self.method, self.results,
                            detector_traces=self._corrected_traces(),
                            theme=self.plot_theme, show_title=False,
                            box_aspect=BOX_ASPECT_LAUDO,
                            medicao_final=self.medicao_final)
        self.canvas.show_figure(fig)
        # so "ESPECTRO": com o painel da tabela aberto o nome da norma
        # nao cabe e colide com os botoes. Ele ja esta no chip do
        # cabecalho e na caixa "Metodo de ensaio".
        self.plot_title.setToolTip(self.method.title or self.method.id)
        self._refresh_table()
        self._refresh_verdict()

    def _refresh_verdict(self):
        """Faixa larga com o resultado geral do ensaio."""
        if not self.traces or not self.results:
            self.verdict_bar.set_estado(
                "neutro", "Sem dados",
                "Importe um trace ou carregue o exemplo sintético.")
            self.header.chip_veredito.set_valor("—", theme.TEXT_DIM)
            return

        vereditos = [r.verdict for r in self.results]
        reprovados = [r for r in self.results if r.verdict.startswith("REPROVADO")]
        indet = [r for r in self.results if r.verdict.startswith("INDET")]

        # Com medicao final, o veredito sai DELA. O prescan e feito em
        # detector de pico, que le o maximo instantaneo: ele ultrapassar
        # o limite de quase-pico nao reprova nada -- so diz onde remedir.
        # Quem reprova e o valor medido com o detector de norma.
        if self.medicao_final is not None and self.medicao_final.pontos:
            self._veredito_por_medicao_final()
            return

        n_fail = sum(1 for p in self.peaks if p.status == "Fail")
        n_ind = sum(1 for p in self.peaks if p.status == "Indet.")
        resumo = f"{len(self.peaks)} pico(s) na tabela · {n_fail} excedendo o limite"
        if n_ind:
            resumo += f" · {n_ind} indeterminado(s)"

        if reprovados:
            pior = min(reprovados, key=lambda r: r.worst_margin_db)
            self.verdict_bar.set_estado(
                "fail", "REPROVADO",
                f"Pior caso {pior.detector}: {pior.worst_margin_db:+.1f} dB em "
                f"{pior.worst_freq_hz/1e6:.3f} MHz  ·  {resumo}")
            self.header.chip_veredito.set_valor("REPROVADO", theme.FAIL)
        elif indet:
            self.verdict_bar.set_estado(
                "warn", "INDETERMINADO",
                f"{', '.join(r.detector for r in indet)} precisa(m) de medição com o "
                f"detector próprio  ·  {resumo}")
            self.header.chip_veredito.set_valor("INDETERMINADO", theme.WARN)
        elif any(v.startswith("INDEFINIDO") for v in vereditos):
            self.verdict_bar.set_estado(
                "neutro", "LIMITE INDEFINIDO",
                "Há detector sem limite carregado/verificado nesta faixa.")
            self.header.chip_veredito.set_valor("INDEFINIDO", theme.TEXT_DIM)
        else:
            pior = min(self.results, key=lambda r: r.worst_margin_db)
            self.verdict_bar.set_estado(
                "ok", "APROVADO",
                f"Menor folga {pior.detector}: {pior.worst_margin_db:+.1f} dB em "
                f"{pior.worst_freq_hz/1e6:.3f} MHz  ·  {resumo}")
            self.header.chip_veredito.set_valor("APROVADO", theme.OK)

    def _veredito_por_medicao_final(self):
        """Veredito baseado nos picos remedidos com o detector de norma."""
        n_fail = sum(1 for p in self.peaks if p.status == "Fail")
        n_ind = sum(1 for p in self.peaks if p.status == "Indet.")
        remedidos = sum(1 for p in self.peaks if p.finais)
        dets = ", ".join(self.medicao_final.detectores)
        base = f"{remedidos} de {len(self.peaks)} pico(s) remedido(s) em {dets}"
        if self.medicao_final.simulada:
            base += "  ·  ⚠ MEDIÇÃO SIMULADA"

        if n_fail:
            pior = min((p for p in self.peaks if p.status == "Fail"),
                        key=lambda p: min((d for d in p.diffs.values()
                                            if d is not None), default=0))
            excesso = max((d for d in pior.diffs.values() if d is not None), default=0.0)
            self.verdict_bar.set_estado(
                "fail", "REPROVADO (medição final)",
                f"{n_fail} pico(s) acima do limite · pior em "
                f"{pior.freq_hz/1e6:.3f} MHz, +{excesso:.1f} dB  ·  {base}")
            self.header.chip_veredito.set_valor("REPROVADO", theme.FAIL)
        elif n_ind:
            self.verdict_bar.set_estado(
                "warn", "INDETERMINADO",
                f"{n_ind} pico(s) sem medição no detector próprio  ·  {base}")
            self.header.chip_veredito.set_valor("INDETERMINADO", theme.WARN)
        else:
            self.verdict_bar.set_estado(
                "ok", "APROVADO (medição final)",
                f"Nenhum pico acima do limite  ·  {base}")
            self.header.chip_veredito.set_valor("APROVADO", theme.OK)

    def _evaluate(self):
        if self.trace is None or self.method is None:
            QMessageBox.information(self, "Faltam dados",
                                     "Importe um arquivo e escolha a norma primeiro.")
            return
        self._refresh_plot()
        self.footer.set_mensagem("Avaliação atualizada.", theme.OK)

    def _refresh_peak_table(self):
        """Monta a tabela 'Picos Detectados' com as mesmas colunas do PDF."""
        detectors = sorted({ll.detector for ll in self.method.limit_lines},
                            key=lambda d: (_DETECTOR_ORDER.get(d, 99), d))
        headers = ["Peak\nNumber", "Frequency\n(MHz)"]
        for det in detectors:
            label = _DETECTOR_LABELS.get(det, det)
            unit = next(ll.unit for ll in self.method.limit_lines if ll.detector == det)
            headers += [f"{label}\n({unit})", f"{label}\nLimit\n({unit})",
                        f"{label}\nDifference\n(dB)"]
        headers.append("Status")

        self.peak_table.clear()
        self.peak_table.setColumnCount(len(headers))
        self.peak_table.setHorizontalHeaderLabels(headers)
        self.peak_table.setRowCount(len(self.peaks))

        negrito = QFont()
        negrito.setBold(True)

        def cell(text: str) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            return item

        for row, peak in enumerate(self.peaks):
            values = [str(row + 1), _br(peak.freq_hz / 1e6, 3)]
            # coluna -> detector, para saber depois quais vieram da
            # medicao final (as colunas continuam iguais as do PDF)
            col_det: dict[int, str] = {}
            for det in detectors:
                col_det[len(values)] = det
                values += [_br(peak.level_for(det), 1), _br(peak.limits.get(det), 1),
                           _br(peak.diffs.get(det), 1)]
            values.append(peak.status)
            ultima = len(values) - 1
            for col, text in enumerate(values):
                item = cell(text)
                if col == 0:
                    item.setForeground(theme.status_color(""))
                if col == ultima:
                    item.setForeground(theme.status_color(peak.status))
                    if peak.status != "Pass":
                        item.setFont(negrito)
                # a coluna "Difference" positiva = ultrapassou o limite
                elif col > 1 and (col - 2) % 3 == 2 and text not in ("-", ""):
                    if not text.startswith("-"):
                        item.setForeground(theme.status_color("Fail"))
                if col in col_det and col_det[col] in peak.finais:
                    item.setFont(negrito)
                    item.setToolTip(
                        "Valor da MEDIÇÃO FINAL: remedido em frequência fixa "
                        f"com o detector {col_det[col]}, e não lido do prescan.")
                self.peak_table.setItem(row, col, item)
        self._ajustar_colunas(self.peak_table)
        n_finais = sum(1 for p in self.peaks if p.finais)
        titulo = f"Picos detectados ({len(self.peaks)})"
        if n_finais:
            titulo += f" · {n_finais} com medição final"
        self.result_tabs.setTabText(0, titulo)
        self._atualizar_contador_tabela()

    def _refresh_table(self):
        self._refresh_peak_table()
        self.result_table.setRowCount(0)
        negrito = QFont()
        negrito.setBold(True)
        for r in self.results:
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            margin_txt = "—" if r.worst_margin_db != r.worst_margin_db else f"{r.worst_margin_db:+.1f}"
            freq_txt = "—" if r.worst_freq_hz != r.worst_freq_hz else f"{r.worst_freq_hz/1e6:.3f} MHz"
            textos = [_DETECTOR_LABELS.get(r.detector, r.detector), margin_txt,
                      freq_txt, r.verdict]
            for col, txt in enumerate(textos):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter if col else
                                       Qt.AlignLeft | Qt.AlignVCenter)
                if col == 3:
                    item.setForeground(theme.status_color(r.verdict))
                    item.setFont(negrito)
                elif col == 1 and margin_txt.startswith("-"):
                    item.setForeground(theme.status_color("Fail"))
                self.result_table.setItem(row, col, item)
        self._ajustar_colunas(self.result_table)

    # ---------------- relatorio ----------------
    def _export_pdf(self):
        if self.trace is None or self.method is None:
            QMessageBox.information(self, "Faltam dados",
                                     "Importe um arquivo e avalie antes de gerar o PDF.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório",
                                               "relatorio_cispr15.pdf", "PDF (*.pdf)")
        if not path:
            return
        info = ReportInfo(
            eut_name=self.eut_name_edit.text(),
            operator=self.operator_edit.text(),
            receiver_model=self.receiver_edit.text(),
            lisn_or_antenna=self.lisn_edit.text(),
        )
        trace = self._corrected_trace()
        outros = self._corrected_traces()
        results = evaluate(trace, self.method, incerteza=self.incerteza,
                            detector_traces=outros,
                            regra_4_1=self.rule41_chk.isChecked())
        out = generate_pdf_report(path, trace, self.method, results, info,
                                   detector_traces=outros,
                                   incerteza=self.incerteza,
                                   regra_4_1=self.rule41_chk.isChecked(),
                                   medicao_final=self.medicao_final)
        self.footer.set_mensagem(f"Relatório gerado: {out}", theme.OK)
        QMessageBox.information(self, "Relatório gerado", f"Salvo em: {out}")
