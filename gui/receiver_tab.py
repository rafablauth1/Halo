"""
gui/receiver_tab.py

Aba "Receiver / GPIB": escolhe o modelo de receiver R&S (catalogo
pre-setado em instruments/receivers/*.json), monta o endereco GPIB/VISA,
e expoe TODAS as configuracoes de receiver pertinentes a um ensaio
CISPR 15 -- tabela de scan por banda CISPR, detectores, tempos, nivel/
atenuacao/pre-amp/pre-seletor, LISN, transdutor e medicao final.

Antes de mandar qualquer coisa para o instrumento, a sub-aba "Comandos
SCPI" mostra exatamente a sequencia que sera enviada, com a explicacao
de cada linha -- de proposito: os comandos pre-setados ainda nao foram
validados contra hardware real (ver instrucoes/03 e 07).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                                QFormLayout, QComboBox, QLabel, QPushButton,
                                QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
                                QTableWidget, QTableWidgetItem, QTabWidget,
                                QMessageBox, QPlainTextEdit, QInputDialog,
                                QHeaderView, QScrollArea, QSizePolicy,
                                QSplitter)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from gui import theme

from instruments.receiver_models import (list_available_receivers, load_receiver,
                                          ReceiverModel)
from instruments.receiver_settings import (ReceiverSettings, ScanRange, CISPR_BANDS,
                                            build_command_sequence, list_available_presets,
                                            load_settings, save_settings, new_preset,
                                            delete_preset, PRESETS_DIR,
                                            dividir_em_bandas_cispr, validar_passo,
                                            passo_maximo_hz)
from core.limits import list_available_methods, load_method
from gui.receiver_models_manager import ReceiverModelsManagerDialog

SCAN_COLS = ["Ativa", "Banda", "Inicio (Hz)", "Fim (Hz)", "RBW (Hz)", "Passo (Hz)",
             "Tempo (s)", "Atten (dB)", "Att auto", "Pre-amp", "Nota"]

DETECTOR_LIST = ["PK", "QP", "AV", "RMS", "CAV", "CRMS"]
TRACE_MODES = ["WRIT", "MAXH", "AVER", "MINH", "VIEW"]
LEVEL_UNITS = ["DBUV", "DBUA", "DBM", "DBPW", "DBUV_M", "DBUA_M"]
LISN_TYPES = ["ENV216", "ESH2Z5", "ESH3Z5", "ENV4200", "ENV432"]
LISN_PHASES = ["L1", "L2", "L3", "N"]
INTERFACES = ["GPIB", "TCPIP", "USB", "ASRL (serial)"]


class ReceiverTab(QWidget):
    """Aba completa de configuracao do receiver."""

    trace_acquired = Signal(object)  # emite um core.trace.Trace apos varredura

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = ReceiverSettings()
        self.model: ReceiverModel | None = None
        self.model_path: Path | None = None
        self.preset_path: Path | None = None
        self._receiver = None  # instancia conectada (RohdeSchwarzEMIReceiver)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)

        # ================= topo: instrumento + conexao + preset =================
        topo = QWidget()
        top = QHBoxLayout(topo)
        top.setContentsMargins(0, 0, 0, 0)

        # ---- instrumento ----
        inst_box = QGroupBox("Instrumento (catálogo R&&S)")
        inst_l = QVBoxLayout(inst_box)
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        inst_l.addWidget(self.model_combo)
        self.model_info = QLabel("-")
        self.model_info.setWordWrap(True)
        # sem isso o rotulo fica com a sobra de altura da caixa e
        # centraliza o texto, abrindo um vao no meio do cartao
        self.model_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.model_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.model_info.setStyleSheet(theme.CSS_MUTED)
        inst_l.addWidget(self.model_info)
        inst_l.addStretch(1)
        manage_btn = QPushButton("Gerenciar modelos…")
        manage_btn.setToolTip("Cadastro de modelos R&S e edicao dos comandos SCPI de cada um.")
        manage_btn.clicked.connect(self._manage_models)
        inst_l.addWidget(manage_btn)
        inst_box.setMinimumHeight(150)
        top.addWidget(inst_box, 2)

        # ---- conexao ----
        conn_box = QGroupBox("Conexão (GPIB / VISA)")
        conn_l = QFormLayout(conn_box)
        self.iface_combo = QComboBox()
        self.iface_combo.addItems(INTERFACES)
        self.iface_combo.currentIndexChanged.connect(self._rebuild_resource)
        conn_l.addRow("Interface", self.iface_combo)
        self.board_spin = QSpinBox()
        self.board_spin.setRange(0, 15)
        self.board_spin.valueChanged.connect(self._rebuild_resource)
        conn_l.addRow("Placa / board", self.board_spin)
        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(0, 30)
        self.addr_spin.setValue(20)
        self.addr_spin.valueChanged.connect(self._rebuild_resource)
        conn_l.addRow("Endereço GPIB", self.addr_spin)
        self.host_edit = QLineEdit("192.168.0.100")
        self.host_edit.textChanged.connect(self._rebuild_resource)
        conn_l.addRow("Host (TCPIP)", self.host_edit)
        self.resource_edit = QLineEdit("GPIB0::20::INSTR")
        conn_l.addRow("Recurso VISA", self.resource_edit)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1000, 300000)
        self.timeout_spin.setSingleStep(1000)
        self.timeout_spin.setValue(20000)
        conn_l.addRow("Timeout (ms)", self.timeout_spin)

        conn_btns = QHBoxLayout()
        for text, slot in (("Listar VISA", self._list_visa), ("Conectar / *IDN?", self._connect),
                            ("Reset", self._reset), ("Erros", self._read_errors)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            conn_btns.addWidget(b)
        conn_l.addRow(conn_btns)
        self.dry_run_chk = QCheckBox("Modo simulação (não abre VISA, só registra os comandos)")
        self.dry_run_chk.setToolTip(
            "Permite exercitar todo o fluxo sem instrumento: os comandos sao registrados "
            "e a varredura devolve um trace sintetico. Use para conferir a sequencia "
            "antes de ir ao laboratorio.")
        conn_l.addRow(self.dry_run_chk)
        self.conn_status = QLabel("Desconectado")
        self.conn_status.setWordWrap(True)
        self.conn_status.setStyleSheet(theme.CSS_MUTED)
        conn_l.addRow(self.conn_status)
        top.addWidget(conn_box, 3)

        # ---- preset ----
        preset_box = QGroupBox("Preset de ensaio")
        preset_l = QVBoxLayout(preset_box)
        self.preset_combo = QComboBox()
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_l.addWidget(self.preset_combo)
        pbtns = QHBoxLayout()
        for text, slot in (("Salvar", self._save_preset), ("Novo", self._new_preset),
                            ("Excluir", self._delete_preset)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            pbtns.addWidget(b)
        preset_l.addLayout(pbtns)
        preset_l.addStretch(1)
        top.addWidget(preset_box, 2)

        # ================= sub-abas de configuracao =================
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMinimumHeight(260)

        # Numa tela 1366x768 o bloco de cima (instrumento + conexao +
        # preset) ocupa ~355 px dos ~540 disponiveis e a tabela de
        # varredura fica num filete de uma linha. Com a divisoria o
        # operador encolhe a configuracao e da espaco a tabela.
        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.setChildrenCollapsible(False)
        self.vsplit.setHandleWidth(8)
        self.vsplit.addWidget(topo)
        self.vsplit.addWidget(self.tabs)
        self.vsplit.setStretchFactor(0, 0)
        self.vsplit.setStretchFactor(1, 1)
        self.vsplit.setSizes([300, 420])
        root.addWidget(self.vsplit, 1)
        self.tabs.addTab(self._build_scan_tab(), "Frequência / Scan")
        self.tabs.addTab(self._build_detector_tab(), "Detector / Tempo")
        self.tabs.addTab(self._build_level_tab(), "Nível / Entrada")
        self.tabs.addTab(self._build_lisn_tab(), "LISN / Transdutor")
        self.tabs.addTab(self._build_final_tab(), "Medição final")
        self.tabs.addTab(self._build_scpi_tab(), "Comandos SCPI")

        # ================= acoes =================
        actions = QHBoxLayout()
        gen_btn = QPushButton("Gerar comandos SCPI")
        gen_btn.clicked.connect(self._generate_commands)
        actions.addWidget(gen_btn)
        self.apply_btn = QPushButton("Aplicar no instrumento")
        self.apply_btn.clicked.connect(self._apply_to_instrument)
        actions.addWidget(self.apply_btn)
        self.scan_btn = QPushButton("Executar varredura e importar")
        self.scan_btn.clicked.connect(self._run_scan)
        actions.addWidget(self.scan_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        self._reload_models()
        self._reload_presets()

    # ---------------------------------------------------------------- sub-abas
    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    def _build_scan_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(
            "Tabela de varredura: uma linha por sub-faixa. As RBW seguem a CISPR 16-1-1 "
            "(Banda A 9-150 kHz: 200 Hz | Banda B 150 kHz-30 MHz: 9 kHz | "
            "Banda C/D 30 MHz-1 GHz: 120 kHz | Banda E >1 GHz: 1 MHz)."))
        self.scan_table = QTableWidget(0, len(SCAN_COLS))
        self.scan_table.setAlternatingRowColors(True)
        self.scan_table.verticalHeader().setDefaultSectionSize(26)
        self.scan_table.setHorizontalHeaderLabels(SCAN_COLS)
        self.scan_table.horizontalHeader().setSectionResizeMode(len(SCAN_COLS) - 1, QHeaderView.Stretch)
        self.scan_table.setMinimumHeight(210)
        l.addWidget(self.scan_table, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton("Adicionar faixa")
        add_btn.clicked.connect(lambda: self._add_scan_row(ScanRange()))
        del_btn = QPushButton("Remover faixa")
        del_btn.clicked.connect(self._del_scan_row)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addSpacing(10)
        rotulo_banda = QLabel("Inserir banda CISPR:")
        rotulo_banda.setStyleSheet(theme.CSS_MUTED)
        btns.addWidget(rotulo_banda)
        for key in ("A", "B", "C", "D", "E"):
            b = QPushButton(key)
            b.setObjectName("compact")
            b.setFixedWidth(36)
            b.setToolTip(f"Adiciona uma linha ja preenchida com a banda CISPR {key}.")
            b.clicked.connect(lambda _=False, k=key: self._add_cispr_band(k))
            btns.addWidget(b)
        btns.addStretch(1)
        l.addLayout(btns)

        # Monta a tabela de scan a partir da faixa da norma escolhida,
        # dividindo automaticamente nas bandas CISPR que ela atravessa.
        norma_row = QHBoxLayout()
        norma_row.addWidget(QLabel("Preencher pela norma:"))
        self.norma_combo = QComboBox()
        for p in list_available_methods():
            try:
                m = load_method(p)
                self.norma_combo.addItem(f"{m.id} ({m.freq_range_hz[0]/1e3:g} kHz – "
                                          f"{m.freq_range_hz[1]/1e6:g} MHz)", str(p))
            except Exception:
                continue
        norma_row.addWidget(self.norma_combo, 1)
        fill_btn = QPushButton("Gerar faixas CISPR")
        fill_btn.setToolTip(
            "Divide a faixa da norma nas bandas CISPR que ela atravessa, cada uma com a "
            "RBW e o passo de norma. Ex.: 9 kHz–30 MHz vira Banda A (RBW 200 Hz) + "
            "Banda B (RBW 9 kHz), porque a largura de banda muda em 150 kHz.")
        fill_btn.clicked.connect(self._fill_from_standard)
        norma_row.addWidget(fill_btn)
        l.addLayout(norma_row)

        self.scan_aviso = QLabel("")
        self.scan_aviso.setWordWrap(True)
        self.scan_aviso.setStyleSheet(theme.CSS_FAIL)
        l.addWidget(self.scan_aviso)

        opts = QGroupBox("Opções de banda")
        opts_l = QFormLayout(opts)
        self.cispr_filter_chk = QCheckBox("Filtro CISPR (largura de 6 dB) — exigido por norma")
        self.cispr_filter_chk.setChecked(True)
        opts_l.addRow(self.cispr_filter_chk)
        self.vbw_auto_chk = QCheckBox("VBW automatica")
        self.vbw_auto_chk.setChecked(True)
        opts_l.addRow(self.vbw_auto_chk)
        self.vbw_spin = QDoubleSpinBox()
        self.vbw_spin.setRange(0, 5e7)
        self.vbw_spin.setDecimals(0)
        self.vbw_spin.setGroupSeparatorShown(True)
        opts_l.addRow("VBW (Hz)", self.vbw_spin)
        self.receiver_mode_chk = QCheckBox("Usar modo Receiver (scan EMI) em vez de analisador")
        self.receiver_mode_chk.setChecked(True)
        opts_l.addRow(self.receiver_mode_chk)
        self.reset_chk = QCheckBox("Enviar *RST antes de configurar")
        self.reset_chk.setChecked(True)
        opts_l.addRow(self.reset_chk)
        l.addWidget(opts)
        return self._wrap_scroll(w)

    def _build_detector_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        det_box = QGroupBox("Detectores simultaneos (um por trace)")
        det_l = QFormLayout(det_box)
        self.det_checks: dict[str, QCheckBox] = {}
        self.det_traces: dict[str, QSpinBox] = {}
        for det in DETECTOR_LIST:
            row = QHBoxLayout()
            chk = QCheckBox(det)
            spin = QSpinBox()
            spin.setRange(1, 6)
            row.addWidget(chk)
            row.addWidget(QLabel("trace"))
            row.addWidget(spin)
            row.addStretch(1)
            holder = QWidget()
            holder.setLayout(row)
            det_l.addRow(holder)
            self.det_checks[det] = chk
            self.det_traces[det] = spin
        det_l.addRow(QLabel(
            "PK = pico | QP = quase-pico | AV = media | RMS | CAV = media CISPR | CRMS = RMS-media"))
        l.addWidget(det_box)

        time_box = QGroupBox("Tempos")
        time_l = QFormLayout(time_box)
        self.meas_time_spin = QDoubleSpinBox()
        self.meas_time_spin.setRange(0.001, 600)
        self.meas_time_spin.setDecimals(3)
        self.meas_time_spin.setValue(1.0)
        time_l.addRow("Tempo de medicao por ponto (s)", self.meas_time_spin)
        time_l.addRow(QLabel("CISPR 16-2-1: tipicamente >= 1 s para quase-pico."))
        self.sweep_auto_chk = QCheckBox("Tempo de varredura automatico")
        self.sweep_auto_chk.setChecked(True)
        time_l.addRow(self.sweep_auto_chk)
        self.sweep_time_spin = QDoubleSpinBox()
        self.sweep_time_spin.setRange(0, 10000)
        self.sweep_time_spin.setDecimals(3)
        time_l.addRow("Tempo de varredura (s)", self.sweep_time_spin)
        self.sweep_points_spin = QSpinBox()
        self.sweep_points_spin.setRange(0, 1000000)
        self.sweep_points_spin.setSpecialValueText("(automatico)")
        time_l.addRow("Pontos por varredura", self.sweep_points_spin)
        self.sweep_count_spin = QSpinBox()
        self.sweep_count_spin.setRange(1, 10000)
        time_l.addRow("Numero de varreduras", self.sweep_count_spin)
        self.hold_time_spin = QDoubleSpinBox()
        self.hold_time_spin.setRange(0, 600)
        self.hold_time_spin.setDecimals(2)
        time_l.addRow("Hold time (s)", self.hold_time_spin)
        l.addWidget(time_box)

        trace_box = QGroupBox("Trace")
        trace_l = QFormLayout(trace_box)
        self.trace_mode_combo = QComboBox()
        self.trace_mode_combo.addItems(TRACE_MODES)
        self.trace_mode_combo.setCurrentText("MAXH")
        trace_l.addRow("Modo do trace", self.trace_mode_combo)
        trace_l.addRow(QLabel("WRIT = clear/write | MAXH = max hold | AVER = media"))
        l.addWidget(trace_box)
        l.addStretch(1)
        return self._wrap_scroll(w)

    def _build_level_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        lvl_box = QGroupBox("Nivel")
        lvl_l = QFormLayout(lvl_box)
        self.ref_level_spin = QDoubleSpinBox()
        self.ref_level_spin.setRange(-200, 200)
        self.ref_level_spin.setValue(100)
        lvl_l.addRow("Nivel de referencia (dB)", self.ref_level_spin)
        self.ref_offset_spin = QDoubleSpinBox()
        self.ref_offset_spin.setRange(-200, 200)
        lvl_l.addRow("Offset de nivel (dB)", self.ref_offset_spin)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(LEVEL_UNITS)
        lvl_l.addRow("Unidade de nivel", self.unit_combo)
        self.autorange_chk = QCheckBox("Auto range")
        self.autorange_chk.setChecked(True)
        lvl_l.addRow(self.autorange_chk)
        l.addWidget(lvl_box)

        att_box = QGroupBox("Atenuacao e amplificacao")
        att_l = QFormLayout(att_box)
        self.att_auto_chk = QCheckBox("Atenuacao RF automatica")
        self.att_auto_chk.setChecked(True)
        att_l.addRow(self.att_auto_chk)
        self.att_spin = QDoubleSpinBox()
        self.att_spin.setRange(0, 100)
        self.att_spin.setSingleStep(5)
        self.att_spin.setValue(10)
        att_l.addRow("Atenuacao RF (dB)", self.att_spin)
        self.preamp_chk = QCheckBox("Pre-amplificador ligado")
        att_l.addRow(self.preamp_chk)
        self.preamp_level_spin = QDoubleSpinBox()
        self.preamp_level_spin.setRange(0, 60)
        self.preamp_level_spin.setSpecialValueText("(padrao)")
        att_l.addRow("Ganho do pre-amp (dB)", self.preamp_level_spin)
        self.presel_chk = QCheckBox("Pre-seletor ligado")
        self.presel_chk.setChecked(True)
        att_l.addRow(self.presel_chk)
        l.addWidget(att_box)

        inp_box = QGroupBox("Entrada de RF")
        inp_l = QFormLayout(inp_box)
        self.imp_combo = QComboBox()
        self.imp_combo.addItems(["50", "75"])
        inp_l.addRow("Impedancia (ohm)", self.imp_combo)
        self.coupling_combo = QComboBox()
        self.coupling_combo.addItems(["AC", "DC"])
        inp_l.addRow("Acoplamento", self.coupling_combo)
        self.limiter_chk = QCheckBox("Limitador de pulso (protege o front-end)")
        inp_l.addRow(self.limiter_chk)
        l.addWidget(inp_box)
        l.addStretch(1)
        return self._wrap_scroll(w)

    def _build_lisn_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        lisn_box = QGroupBox("LISN / AMN controlada pelo receiver")
        lisn_l = QFormLayout(lisn_box)
        self.lisn_chk = QCheckBox("Controlar a LISN pelo receiver")
        lisn_l.addRow(self.lisn_chk)
        self.lisn_type_combo = QComboBox()
        self.lisn_type_combo.addItems(LISN_TYPES)
        lisn_l.addRow("Tipo de LISN", self.lisn_type_combo)
        self.lisn_phase_combo = QComboBox()
        self.lisn_phase_combo.addItems(LISN_PHASES)
        lisn_l.addRow("Fase medida", self.lisn_phase_combo)
        self.lisn_pe_chk = QCheckBox("Terra de protecao (PE) aterrado")
        self.lisn_pe_chk.setChecked(True)
        lisn_l.addRow(self.lisn_pe_chk)
        self.lisn_hp_chk = QCheckBox("Filtro passa-alta 150 kHz")
        lisn_l.addRow(self.lisn_hp_chk)
        lisn_l.addRow(QLabel(
            "CISPR 15 item 8: medir fase e neutro, um de cada vez. Trocar a fase aqui "
            "e repetir a varredura para cada condutor."))
        l.addWidget(lisn_box)

        tr_box = QGroupBox("Transdutor (fator de antena / LISN / cabo gravado no receiver)")
        tr_l = QFormLayout(tr_box)
        self.transducer_chk = QCheckBox("Ativar transdutor no instrumento")
        tr_l.addRow(self.transducer_chk)
        self.transducer_edit = QLineEdit()
        self.transducer_edit.setPlaceholderText("nome do fator gravado no receiver")
        tr_l.addRow("Nome do transdutor", self.transducer_edit)
        tr_l.addRow(QLabel(
            "Alternativa: deixar desligado aqui e aplicar as correcoes no proprio software, "
            "pela aba de analise (Gerenciar tabelas de correcao)."))
        l.addWidget(tr_box)
        l.addStretch(1)
        return self._wrap_scroll(w)

    def _build_final_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        box = QGroupBox("Medicao final (peak search -> remedicao em QP/AV)")
        f = QFormLayout(box)
        self.final_chk = QCheckBox("Executar medicao final apos a varredura")
        self.final_chk.setChecked(True)
        f.addRow(self.final_chk)
        self.final_margin_spin = QDoubleSpinBox()
        self.final_margin_spin.setRange(0, 60)
        self.final_margin_spin.setValue(6)
        f.addRow("Margem abaixo do limite (dB)", self.final_margin_spin)
        self.final_peaks_spin = QSpinBox()
        self.final_peaks_spin.setRange(1, 200)
        self.final_peaks_spin.setValue(10)
        f.addRow("Quantidade de picos", self.final_peaks_spin)
        self.final_det_checks: dict[str, QCheckBox] = {}
        row = QHBoxLayout()
        for det in ("QP", "AV", "CAV", "CRMS"):
            chk = QCheckBox(det)
            self.final_det_checks[det] = chk
            row.addWidget(chk)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        f.addRow("Detectores da medicao final", holder)
        f.addRow(QLabel(
            "E o mesmo criterio descrito nos relatorios do laboratorio: os picos dentro de "
            "6 dB do limite de quase-pico sao remedidos com o detector de norma."))
        l.addWidget(box)
        l.addStretch(1)
        return self._wrap_scroll(w)

    def _build_scpi_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(
            "Sequencia que sera enviada ao instrumento. Confira antes de aplicar — "
            "os comandos pre-setados NAO foram validados contra hardware real."))
        self.scpi_view = QPlainTextEdit()
        self.scpi_view.setReadOnly(True)
        self.scpi_view.setFont(QFont("Consolas", 9))
        l.addWidget(self.scpi_view, 1)
        return w

    # ---------------------------------------------------------------- modelos
    def _reload_models(self):
        current = self.model_path
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for p in list_available_receivers():
            try:
                m = load_receiver(p)
                label = f"{m.model or p.stem}  —  {m.description}"
            except Exception:
                label = p.stem
            self.model_combo.addItem(label, str(p))
        self.model_combo.blockSignals(False)
        idx = self.model_combo.findData(str(current)) if current else -1
        self.model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._on_model_changed()

    def _on_model_changed(self):
        idx = self.model_combo.currentIndex()
        if idx < 0:
            return
        self.model_path = Path(self.model_combo.itemData(idx))
        self.model = load_receiver(self.model_path)
        m = self.model

        def ghz(v: float) -> str:
            if v >= 1e9:
                return f"{v/1e9:g} GHz"
            if v >= 1e6:
                return f"{v/1e6:g} MHz"
            if v >= 1e3:
                return f"{v/1e3:g} kHz"
            return f"{v:g} Hz"

        caps = []
        if m.has_receiver_mode:
            caps.append("modo receiver")
        if m.has_scan_table:
            caps.append("tabela de scan")
        if m.has_preamp:
            caps.append("pre-amp")
        if m.has_preselector:
            caps.append("pre-seletor")
        if m.has_lisn_control:
            caps.append("controle de LISN")
        verified = "comandos conferidos" if m.verified else "comandos NAO conferidos no manual"
        self.model_info.setText(
            f"{m.manufacturer} {m.model} · {ghz(m.freq_min_hz)} – {ghz(m.freq_max_hz)}\n"
            f"Detectores: {', '.join(m.detectors)}\n"
            f"Recursos: {', '.join(caps) if caps else '-'}\n"
            f"⚠ {verified}")
        self.addr_spin.blockSignals(True)
        self.addr_spin.setValue(m.default_gpib_address)
        self.addr_spin.blockSignals(False)
        self._rebuild_resource()

    def _manage_models(self):
        dlg = ReceiverModelsManagerDialog(self)
        dlg.exec()
        if dlg.changed:
            self._reload_models()

    # ---------------------------------------------------------------- conexao
    def _rebuild_resource(self):
        iface = self.iface_combo.currentText()
        board = self.board_spin.value()
        if iface == "GPIB":
            res = f"GPIB{board}::{self.addr_spin.value()}::INSTR"
        elif iface == "TCPIP":
            res = f"TCPIP{board}::{self.host_edit.text().strip()}::INSTR"
        elif iface == "USB":
            res = f"USB{board}::0x0AAD::INSTR"
        else:
            res = f"ASRL{board}::INSTR"
        self.resource_edit.setText(res)

    def _list_visa(self):
        try:
            from instruments.scpi_receiver import list_visa_resources
            resources = list_visa_resources()
        except Exception as e:
            QMessageBox.warning(self, "VISA", f"Nao consegui listar recursos VISA:\n{e}")
            return
        if not resources:
            QMessageBox.information(
                self, "VISA",
                "Nenhum recurso VISA encontrado.\n\n"
                "Para GPIB e preciso ter uma interface GPIB (ex.: NI GPIB-USB-HS ou "
                "R&S) com o driver VISA da fabricante instalado (NI-VISA ou R&S VISA). "
                "O pyvisa-py sozinho nao fala GPIB.")
            return
        choice, ok = QInputDialog.getItem(self, "Recursos VISA encontrados",
                                           "Selecione:", resources, 0, False)
        if ok and choice:
            self.resource_edit.setText(choice)

    def _get_receiver(self):
        from instruments.scpi_receiver import RohdeSchwarzEMIReceiver, ReceiverConfig
        dry = self.dry_run_chk.isChecked()
        # troca de modelo/recurso/modo obriga a reabrir a sessao
        if (self._receiver is not None and
                (self._receiver.config.dry_run != dry
                 or self._receiver.config.resource != self.resource_edit.text().strip()
                 or self._receiver.model is not self.model)):
            try:
                self._receiver.disconnect()
            except Exception:
                pass
            self._receiver = None
        if self._receiver is None:
            cfg = ReceiverConfig(resource=self.resource_edit.text().strip(),
                                  timeout_ms=self.timeout_spin.value(),
                                  model=self.model, dry_run=dry)
            self._receiver = RohdeSchwarzEMIReceiver(cfg)
            self._receiver.connect()
        return self._receiver

    def _connect(self):
        try:
            rec = self._get_receiver()
            idn = rec.idn()
        except Exception as e:
            self._receiver = None
            self.conn_status.setText(f"Falha: {e}")
            self.conn_status.setStyleSheet(theme.CSS_FAIL)
            return
        self.conn_status.setText(f"Conectado: {idn}")
        self.conn_status.setStyleSheet(theme.CSS_OK)

    def _reset(self):
        try:
            self._get_receiver().reset()
        except Exception as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.conn_status.setText("Instrumento resetado (*RST).")

    def _read_errors(self):
        try:
            errors = self._get_receiver().check_errors()
        except Exception as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        QMessageBox.information(self, "Fila de erros",
                                 "\n".join(errors) if errors else "Nenhum erro na fila.")

    # ---------------------------------------------------------------- presets
    def _reload_presets(self):
        current = self.preset_path
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for p in list_available_presets():
            try:
                s = load_settings(p)
                label = s.name or p.stem
            except Exception:
                label = p.stem
            self.preset_combo.addItem(label, str(p))
        self.preset_combo.blockSignals(False)
        idx = self.preset_combo.findData(str(current)) if current else -1
        self.preset_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._on_preset_changed()

    def _on_preset_changed(self):
        idx = self.preset_combo.currentIndex()
        if idx < 0:
            return
        self.preset_path = Path(self.preset_combo.itemData(idx))
        try:
            self.settings = load_settings(self.preset_path)
        except Exception as e:
            QMessageBox.warning(self, "Erro ao carregar preset", str(e))
            return
        self._settings_to_ui()

    def _save_preset(self):
        if self.preset_path is None:
            return
        self._ui_to_settings()
        save_settings(self.settings, self.preset_path)
        QMessageBox.information(self, "Salvo", f"Preset salvo em {self.preset_path.name}")
        self._reload_presets()

    def _new_preset(self):
        name, ok = QInputDialog.getText(self, "Novo preset", "Nome:")
        if not ok or not name.strip():
            return
        self._ui_to_settings()
        try:
            path = new_preset(name, base=self.settings)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.preset_path = path
        self._reload_presets()

    def _delete_preset(self):
        if self.preset_path is None:
            return
        if QMessageBox.question(self, "Confirmar exclusao",
                                 f"Excluir o preset '{self.preset_path.stem}'?") != QMessageBox.Yes:
            return
        delete_preset(self.preset_path)
        self.preset_path = None
        self._reload_presets()

    # ---------------------------------------------------------------- scan rows
    def _add_scan_row(self, rng: ScanRange):
        row = self.scan_table.rowCount()
        self.scan_table.insertRow(row)

        chk = QCheckBox()
        chk.setChecked(rng.enabled)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.addWidget(chk)
        hl.setAlignment(Qt.AlignCenter)
        hl.setContentsMargins(0, 0, 0, 0)
        self.scan_table.setCellWidget(row, 0, holder)

        band_combo = QComboBox()
        band_combo.addItems(list(CISPR_BANDS.keys()))
        band_combo.setCurrentText(rng.band if rng.band in CISPR_BANDS else "B")
        # trocar a banda repoe RBW, passo e faixa conforme a norma
        band_combo.currentTextChanged.connect(
            lambda chave, c=band_combo: self._on_band_changed(chave, c))
        self.scan_table.setCellWidget(row, 1, band_combo)

        for col, val in ((2, rng.start_hz), (3, rng.stop_hz), (4, rng.rbw_hz),
                          (5, rng.step_hz), (6, rng.meas_time_s), (7, rng.attenuation_db)):
            self.scan_table.setItem(row, col, QTableWidgetItem(f"{val:g}"))

        att_chk = QCheckBox()
        att_chk.setChecked(rng.attenuation_auto)
        att_holder = QWidget()
        al = QHBoxLayout(att_holder)
        al.addWidget(att_chk)
        al.setAlignment(Qt.AlignCenter)
        al.setContentsMargins(0, 0, 0, 0)
        self.scan_table.setCellWidget(row, 8, att_holder)

        pre_chk = QCheckBox()
        pre_chk.setChecked(rng.preamp)
        pre_holder = QWidget()
        pl = QHBoxLayout(pre_holder)
        pl.addWidget(pre_chk)
        pl.setAlignment(Qt.AlignCenter)
        pl.setContentsMargins(0, 0, 0, 0)
        self.scan_table.setCellWidget(row, 9, pre_holder)

        self.scan_table.setItem(row, 10, QTableWidgetItem(rng.note))

    def _del_scan_row(self):
        rows = sorted({i.row() for i in self.scan_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.scan_table.removeRow(r)

    def _add_cispr_band(self, key: str):
        band = CISPR_BANDS[key]
        self._add_scan_row(ScanRange(band=key, start_hz=band.freq_min_hz,
                                      stop_hz=band.freq_max_hz, rbw_hz=band.rbw_hz,
                                      step_hz=band.step_hz, note=band.note))
        self._validar_faixas()

    def _row_of_widget(self, widget) -> int:
        for r in range(self.scan_table.rowCount()):
            if self.scan_table.cellWidget(r, 1) is widget:
                return r
        return -1

    def _on_band_changed(self, chave: str, combo):
        """Trocar a banda repoe RBW, passo e limites de frequencia da norma."""
        row = self._row_of_widget(combo)
        if row < 0 or chave not in CISPR_BANDS:
            return
        band = CISPR_BANDS[chave]
        for col, val in ((2, band.freq_min_hz), (3, band.freq_max_hz),
                          (4, band.rbw_hz), (5, band.step_hz)):
            self.scan_table.setItem(row, col, QTableWidgetItem(f"{val:g}"))
        item = self.scan_table.item(row, 10)
        if item is None or not item.text().strip():
            self.scan_table.setItem(row, 10, QTableWidgetItem(band.note))
        self._validar_faixas()

    def _fill_from_standard(self):
        """Monta a tabela de scan a partir da faixa da norma escolhida."""
        idx = self.norma_combo.currentIndex()
        if idx < 0:
            return
        try:
            method = load_method(Path(self.norma_combo.itemData(idx)))
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Nao consegui carregar a norma:\n{e}")
            return
        f0, f1 = method.freq_range_hz
        faixas = dividir_em_bandas_cispr(
            f0, f1, meas_time_s=self.meas_time_spin.value(),
            detectors=[d for d, chk in self.det_checks.items() if chk.isChecked()] or None)
        if not faixas:
            QMessageBox.warning(self, "Sem bandas",
                                 "A faixa desta norma nao cai em nenhuma banda CISPR.")
            return
        self.scan_table.setRowCount(0)
        for rng in faixas:
            self._add_scan_row(rng)
        self._validar_faixas()
        resumo = "\n".join(
            f"  Banda {r.band}: {r.start_hz/1e3:g} kHz – {r.stop_hz/1e6:g} MHz · "
            f"RBW {r.rbw_hz:g} Hz · passo {r.step_hz:g} Hz" for r in faixas)
        QMessageBox.information(
            self, "Faixas geradas",
            f"{method.id}\n{f0/1e3:g} kHz – {f1/1e6:g} MHz dividido em "
            f"{len(faixas)} banda(s) CISPR:\n\n{resumo}")

    def _validar_faixas(self):
        """CISPR 16-2-1: o passo nao pode passar de metade da RBW. Marca em
        vermelho as celulas fora da regra e resume o problema abaixo."""
        problemas = []
        for row in range(self.scan_table.rowCount()):
            def num(col: int) -> float:
                item = self.scan_table.item(row, col)
                try:
                    return float(item.text().replace(",", ".")) if item else 0.0
                except ValueError:
                    return 0.0
            rbw, passo = num(4), num(5)
            item_passo = self.scan_table.item(row, 5)
            if item_passo is None or rbw <= 0:
                continue
            msg = validar_passo(rbw, passo)
            if msg:
                item_passo.setForeground(Qt.red)
                item_passo.setToolTip(f"maximo permitido: {passo_maximo_hz(rbw):g} Hz")
                problemas.append(f"faixa {row + 1}: {msg}")
            else:
                item_passo.setForeground(Qt.black)
                item_passo.setToolTip("")
        self.scan_aviso.setText("⚠ " + " | ".join(problemas) if problemas else "")

    def _read_scan_rows(self) -> list[ScanRange]:
        ranges = []
        for row in range(self.scan_table.rowCount()):
            def cell(col: int, default: float = 0.0) -> float:
                item = self.scan_table.item(row, col)
                try:
                    return float(item.text().replace(",", ".")) if item else default
                except ValueError:
                    return default

            enabled_holder = self.scan_table.cellWidget(row, 0)
            enabled = enabled_holder.findChild(QCheckBox).isChecked() if enabled_holder else True
            band_combo = self.scan_table.cellWidget(row, 1)
            band = band_combo.currentText() if band_combo else "B"
            att_holder = self.scan_table.cellWidget(row, 8)
            att_auto = att_holder.findChild(QCheckBox).isChecked() if att_holder else True
            pre_holder = self.scan_table.cellWidget(row, 9)
            preamp = pre_holder.findChild(QCheckBox).isChecked() if pre_holder else False
            note_item = self.scan_table.item(row, 10)

            ranges.append(ScanRange(
                enabled=enabled, band=band,
                start_hz=cell(2), stop_hz=cell(3), rbw_hz=cell(4),
                step_hz=cell(5), meas_time_s=cell(6, 1.0),
                attenuation_db=cell(7, 10.0), attenuation_auto=att_auto,
                preamp=preamp, note=note_item.text() if note_item else "",
            ))
        return ranges

    # ---------------------------------------------------------------- ui <-> settings
    def _settings_to_ui(self):
        s = self.settings

        self.scan_table.setRowCount(0)
        for rng in s.scan_ranges:
            self._add_scan_row(rng)
        self._validar_faixas()

        self.cispr_filter_chk.setChecked(s.rbw_filter_cispr)
        self.vbw_auto_chk.setChecked(s.vbw_auto)
        self.vbw_spin.setValue(s.vbw_hz or 0)
        self.receiver_mode_chk.setChecked(s.receiver_mode)
        self.reset_chk.setChecked(s.reset_before_config)

        for det, chk in self.det_checks.items():
            chk.setChecked(det in s.detectors)
            self.det_traces[det].setValue(s.detector_trace_map.get(det, 1))

        self.meas_time_spin.setValue(s.meas_time_s)
        self.sweep_auto_chk.setChecked(s.sweep_time_auto)
        self.sweep_time_spin.setValue(s.sweep_time_s or 0)
        self.sweep_points_spin.setValue(s.sweep_points or 0)
        self.sweep_count_spin.setValue(s.sweep_count)
        self.hold_time_spin.setValue(s.hold_time_s)
        self.trace_mode_combo.setCurrentText(s.trace_mode)

        self.ref_level_spin.setValue(s.ref_level_dbuv)
        self.ref_offset_spin.setValue(s.ref_level_offset_db)
        self.unit_combo.setCurrentText(s.level_unit)
        self.autorange_chk.setChecked(s.auto_range)
        self.att_auto_chk.setChecked(s.attenuation_auto)
        self.att_spin.setValue(s.attenuation_db)
        self.preamp_chk.setChecked(s.preamp)
        self.preamp_level_spin.setValue(s.preamp_level_db or 0)
        self.presel_chk.setChecked(s.preselector)
        self.imp_combo.setCurrentText(str(s.input_impedance_ohm))
        self.coupling_combo.setCurrentText(s.input_coupling)
        self.limiter_chk.setChecked(s.noise_pulse_limiter)

        self.lisn_chk.setChecked(s.lisn_control)
        self.lisn_type_combo.setCurrentText(s.lisn_type)
        self.lisn_phase_combo.setCurrentText(s.lisn_phase)
        self.lisn_pe_chk.setChecked(s.lisn_pe_grounded)
        self.lisn_hp_chk.setChecked(s.lisn_highpass_150k)
        self.transducer_chk.setChecked(s.transducer_enabled)
        self.transducer_edit.setText(s.transducer_name)

        self.final_chk.setChecked(s.final_measurement)
        self.final_margin_spin.setValue(s.final_meas_margin_db)
        self.final_peaks_spin.setValue(s.final_meas_max_peaks)
        for det, chk in self.final_det_checks.items():
            chk.setChecked(det in s.final_meas_detectors)

        if s.visa_resource:
            self.resource_edit.setText(s.visa_resource)
        self.timeout_spin.setValue(s.timeout_ms)

    def _ui_to_settings(self):
        s = self.settings
        s.scan_ranges = self._read_scan_rows()
        s.rbw_filter_cispr = self.cispr_filter_chk.isChecked()
        s.vbw_auto = self.vbw_auto_chk.isChecked()
        s.vbw_hz = self.vbw_spin.value() or None
        s.receiver_mode = self.receiver_mode_chk.isChecked()
        s.reset_before_config = self.reset_chk.isChecked()

        s.detectors = [d for d, chk in self.det_checks.items() if chk.isChecked()]
        s.detector_trace_map = {d: self.det_traces[d].value() for d in s.detectors}

        s.meas_time_s = self.meas_time_spin.value()
        s.sweep_time_auto = self.sweep_auto_chk.isChecked()
        s.sweep_time_s = self.sweep_time_spin.value() or None
        s.sweep_points = self.sweep_points_spin.value() or None
        s.sweep_count = self.sweep_count_spin.value()
        s.hold_time_s = self.hold_time_spin.value()
        s.trace_mode = self.trace_mode_combo.currentText()

        s.ref_level_dbuv = self.ref_level_spin.value()
        s.ref_level_offset_db = self.ref_offset_spin.value()
        s.level_unit = self.unit_combo.currentText()
        s.auto_range = self.autorange_chk.isChecked()
        s.attenuation_auto = self.att_auto_chk.isChecked()
        s.attenuation_db = self.att_spin.value()
        s.preamp = self.preamp_chk.isChecked()
        s.preamp_level_db = self.preamp_level_spin.value() or None
        s.preselector = self.presel_chk.isChecked()
        s.input_impedance_ohm = int(self.imp_combo.currentText())
        s.input_coupling = self.coupling_combo.currentText()
        s.noise_pulse_limiter = self.limiter_chk.isChecked()

        s.lisn_control = self.lisn_chk.isChecked()
        s.lisn_type = self.lisn_type_combo.currentText()
        s.lisn_phase = self.lisn_phase_combo.currentText()
        s.lisn_pe_grounded = self.lisn_pe_chk.isChecked()
        s.lisn_highpass_150k = self.lisn_hp_chk.isChecked()
        s.transducer_enabled = self.transducer_chk.isChecked()
        s.transducer_name = self.transducer_edit.text().strip()

        s.final_measurement = self.final_chk.isChecked()
        s.final_meas_margin_db = self.final_margin_spin.value()
        s.final_meas_max_peaks = self.final_peaks_spin.value()
        s.final_meas_detectors = [d for d, chk in self.final_det_checks.items() if chk.isChecked()]

        s.visa_resource = self.resource_edit.text().strip()
        s.timeout_ms = self.timeout_spin.value()

    # ---------------------------------------------------------------- acoes
    def _generate_commands(self) -> list[tuple[str, str]]:
        if self.model is None:
            return []
        self._ui_to_settings()
        seq = build_command_sequence(self.settings, self.model)
        lines = [f"# Modelo: {self.model.manufacturer} {self.model.model} ({self.model.family})",
                 f"# Recurso VISA: {self.settings.visa_resource}",
                 f"# {len(seq)} comandos", ""]
        for desc, cmd in seq:
            lines.append(f"{cmd:<48s} # {desc}")
        self.scpi_view.setPlainText("\n".join(lines))
        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        return seq

    def _apply_to_instrument(self):
        seq = self._generate_commands()
        if not seq:
            return
        if not self.model.verified:
            resp = QMessageBox.warning(
                self, "Comandos nao verificados",
                f"Os comandos SCPI do modelo {self.model.model} ainda NAO foram conferidos "
                "contra o manual deste instrumento.\n\nEnviar assim mesmo?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
        try:
            rec = self._get_receiver()
        except Exception as e:
            QMessageBox.warning(self, "Sem conexao", f"Conecte o instrumento primeiro.\n\n{e}")
            return

        sent, failed = 0, []
        for desc, cmd in seq:
            try:
                rec._write(cmd)
                sent += 1
            except Exception as e:
                failed.append(f"{cmd} -> {e}")

        errors = []
        try:
            errors = rec.check_errors()
        except Exception:
            pass

        msg = f"{sent} de {len(seq)} comandos enviados."
        if failed:
            msg += "\n\nFalharam:\n" + "\n".join(failed[:10])
        if errors:
            msg += "\n\nFila de erros do instrumento:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Configuracao aplicada", msg)

    def _run_scan(self):
        self._ui_to_settings()
        try:
            rec = self._get_receiver()
        except Exception as e:
            QMessageBox.warning(self, "Sem conexao", f"Conecte o instrumento primeiro.\n\n{e}")
            return
        try:
            from instruments.acquisition import run_multi_band_scan, ScanBand
            bands = [ScanBand(start_hz=r.start_hz, stop_hz=r.stop_hz, rbw_hz=r.rbw_hz,
                               sweep_time_s=r.meas_time_s)
                     for r in self.settings.scan_ranges if r.enabled]
            if not bands:
                QMessageBox.information(self, "Sem faixas", "Ative pelo menos uma faixa de scan.")
                return
            detector = self.settings.detectors[0] if self.settings.detectors else "QP"
            unit = "dBuV" if self.settings.level_unit.startswith("DBUV") else "dBuA"
            trace = run_multi_band_scan(rec, bands, detector=detector, unit=unit)
        except Exception as e:
            QMessageBox.warning(self, "Erro na varredura", str(e))
            return
        self.trace_acquired.emit(trace)
        QMessageBox.information(self, "Varredura concluida",
                                 f"{len(trace.freq_hz)} pontos importados para a aba de analise.")
