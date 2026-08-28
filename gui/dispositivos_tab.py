"""
gui/dispositivos_tab.py

Aba "Dispositivos" -- a aba Devices do RadiMation.

A esquerda, a arvore: grupo > tipo > dispositivo, com a situacao do
certificado colorida. A direita, a ficha do dispositivo selecionado, em
cinco partes:

  Identificacao   quem e o aparelho
  Conexao         como se fala com ele (o recurso VISA sai daqui)
  Comandos        o dicionario SCPI, editavel
  Certificados    calibracao e os pontos de correcao
  Notas           o que se aprendeu usando

Isto substitui a antiga tela de Configuracoes, que listava enderecos GPIB
soltos -- "Endereco GPIB do UCS", "Endereco GPIB do Chroma" -- sem a ficha
a que esses enderecos pertencem. O endereco e um CAMPO do dispositivo, nao
uma configuracao do programa.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                                QTreeWidget, QTreeWidgetItem, QTabWidget,
                                QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
                                QCheckBox, QPushButton, QLabel, QTableWidget,
                                QTableWidgetItem, QHeaderView, QMessageBox,
                                QInputDialog, QPlainTextEdit, QDateEdit,
                                QFileDialog, QGroupBox)

from gui import theme
from gui.widgets import Badge, GradeCampos
from core.dispositivos import (TIPOS, GRUPOS, tipos_do_grupo, Dispositivo,
                                Conexao, INTERFACES, todos, salvar, excluir,
                                carregar, caminho, migrar_tudo)
from core.equipamentos import Certificado, PontoCertificado

COR_SITUACAO = {"ok": "verde", "vence_em_breve": "ambar",
                "vencido": "vermelho", "sem_certificado": "cinza"}
TEXTO_SITUACAO = {"ok": "CALIBRADO", "vence_em_breve": "VENCE EM BREVE",
                  "vencido": "VENCIDO", "sem_certificado": "SEM CERTIFICADO"}

PONTO_COLS = ["Frequência (Hz)", "Valor (dB)", "Incerteza U (dB)"]


class DispositivosTab(QWidget):
    """Cadastro único de dispositivos, no modelo Device Driver."""

    catalogo_mudou = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.atual: Dispositivo | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 4, 0, 0)
        div = QSplitter(Qt.Horizontal)
        div.setChildrenCollapsible(False)
        div.setHandleWidth(8)
        raiz.addWidget(div)

        # ------------------------------ arvore ------------------------------
        esq = QWidget()
        esq_l = QVBoxLayout(esq)
        esq_l.setContentsMargins(2, 0, 8, 6)
        esq_l.setSpacing(7)

        cab = QHBoxLayout()
        titulo = QLabel("DISPOSITIVOS")
        titulo.setObjectName("cardTitle")
        cab.addWidget(titulo)
        cab.addStretch(1)
        self.contagem = QLabel("")
        self.contagem.setStyleSheet(theme.CSS_DIM)
        cab.addWidget(self.contagem)
        esq_l.addLayout(cab)

        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText("filtrar por fabricante, modelo ou série…")
        self.filtro.setClearButtonEnabled(True)
        self.filtro.textChanged.connect(self._montar_arvore)
        esq_l.addWidget(self.filtro)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.setColumnCount(1)
        self.arvore.currentItemChanged.connect(self._ao_selecionar)
        esq_l.addWidget(self.arvore, 1)

        botoes = QHBoxLayout()
        botoes.setSpacing(6)
        for texto, slot in (("Novo", self._novo), ("Duplicar", self._duplicar),
                             ("Excluir", self._excluir)):
            b = QPushButton(texto)
            if texto == "Excluir":
                b.setObjectName("danger")
            b.clicked.connect(slot)
            botoes.addWidget(b)
        esq_l.addLayout(botoes)

        b_biblio = QPushButton("Restaurar biblioteca de fábrica")
        b_biblio.setToolTip(
            "Recria as fichas dos aparelhos que já vêm com o programa "
            "(receptores R&&S e instrumentos da seção EMC).\n"
            "Não mexe em ficha nenhuma que já exista — endereço, número de "
            "série e certificados que você preencheu ficam como estão.")
        b_biblio.clicked.connect(self._restaurar_biblioteca)
        esq_l.addWidget(b_biblio)
        div.addWidget(esq)

        # ------------------------------ ficha ------------------------------
        dir_ = QWidget()
        dir_l = QVBoxLayout(dir_)
        dir_l.setContentsMargins(8, 0, 2, 6)
        dir_l.setSpacing(9)

        topo = QHBoxLayout()
        topo.setSpacing(9)
        self.rotulo = QLabel("Nenhum dispositivo selecionado")
        self.rotulo.setStyleSheet(
            f"color:{theme.TEXT}; font-size:15px; font-weight:600;")
        topo.addWidget(self.rotulo, 1)
        self.badge_situacao = Badge("—", "cinza")
        topo.addWidget(self.badge_situacao)
        self.badge_verificado = Badge("NÃO VALIDADO", "ambar")
        self.badge_verificado.setToolTip(
            "Se os comandos deste aparelho já foram conferidos contra o "
            "hardware de verdade.")
        topo.addWidget(self.badge_verificado)
        dir_l.addLayout(topo)

        self.abas = QTabWidget()
        self.abas.setDocumentMode(True)
        self.abas.addTab(self._aba_identificacao(), "Identificação")
        self.abas.addTab(self._aba_conexao(), "Conexão")
        self.abas.addTab(self._aba_comandos(), "Comandos")
        self.abas.addTab(self._aba_certificados(), "Certificados")
        self.abas.addTab(self._aba_notas(), "Notas")
        dir_l.addWidget(self.abas, 1)

        rodape = QHBoxLayout()
        self.aviso = QLabel("")
        self.aviso.setStyleSheet(theme.CSS_MUTED)
        rodape.addWidget(self.aviso, 1)
        b_salvar = QPushButton("Salvar dispositivo")
        b_salvar.setObjectName("primary")
        b_salvar.setMinimumHeight(34)
        b_salvar.clicked.connect(self._salvar)
        rodape.addWidget(b_salvar)
        dir_l.addLayout(rodape)

        div.addWidget(dir_)
        div.setStretchFactor(0, 0)
        div.setStretchFactor(1, 1)
        div.setSizes([330, 900])

        self._semear_se_vazio()
        self._montar_arvore()
        self._habilitar(False)

    # -------------------------------------------------- biblioteca de fabrica
    def _semear_se_vazio(self):
        """Primeira execução numa máquina nova: monta o cadastro sozinho.

        As fichas ficam em dados/dispositivos/, que é de propósito mantido
        fora do repositório (traz número de série, patrimônio e certificados
        do laboratório). Então num PC recém-clonado a pasta chega vazia, e
        sem isto a aba abriria sem nenhum aparelho. A biblioteca de fábrica
        é reconstruída a partir do que vem junto do programa; o que é do
        laboratório continua tendo que ser copiado à mão."""
        try:
            if not todos():
                migrar_tudo()
        except Exception:
            pass   # cadastro vazio é ruim, mas não impede a aba de abrir

    def _restaurar_biblioteca(self):
        try:
            n = migrar_tudo()
        except Exception as e:
            QMessageBox.warning(self, "Restaurar biblioteca",
                                f"Não deu para recriar as fichas:\n{e}")
            return
        total = sum(n.values())
        self._montar_arvore()
        if total:
            self.catalogo_mudou.emit()
            QMessageBox.information(
                self, "Restaurar biblioteca",
                f"{total} ficha(s) recriada(s):\n"
                f"· {n['receivers']} receptor(es)\n"
                f"· {n['instrumentos_emc']} instrumento(s) da seção EMC\n"
                f"· {n['equipamentos']} equipamento(s) do laboratório")
        else:
            QMessageBox.information(
                self, "Restaurar biblioteca",
                "Nada a recriar — todas as fichas de fábrica já estão no "
                "cadastro. As que você já tinha não foram alteradas.")

    # ------------------------------------------------------------ sub-abas
    def _aba_identificacao(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        g = GradeCampos(3)
        self.tipo_combo = QComboBox()
        for grupo in GRUPOS:
            for t in tipos_do_grupo(grupo):
                self.tipo_combo.addItem(f"{grupo} · {t.nome}", t.id)
        self.tipo_combo.currentIndexChanged.connect(self._ao_trocar_tipo)
        g.add("Tipo", self.tipo_combo, span=3)
        self.fabricante = QLineEdit(); g.add("Fabricante", self.fabricante)
        self.modelo = QLineEdit();     g.add("Modelo", self.modelo)
        self.serie = QLineEdit();      g.add("Número de série", self.serie)
        self.patrimonio = QLineEdit(); g.add("Patrimônio", self.patrimonio)
        self.aplicar = QComboBox()
        self.aplicar.addItems(["somar", "subtrair"])
        self.aplicar.setToolTip(
            "Como a correção entra: nível corrigido = leitura + correção.\n"
            "Perdas (cabo, atenuador, LISN) e fator de antena SOMAM.\n"
            "Ganho de pré-amplificador SUBTRAI.")
        g.add("Correção", self.aplicar)
        self.descricao = QLineEdit(); g.add("Descrição", self.descricao, span=3)
        l.addWidget(g)

        linha = QHBoxLayout()
        self.ativo = QCheckBox("Disponível para uso")
        self.verificado = QCheckBox("Comandos validados contra o hardware")
        self.verificado.setToolTip(
            "Marque só depois de confirmar no aparelho de verdade.\n"
            "É o que separa um comando testado de uma tentativa.")
        linha.addWidget(self.ativo)
        linha.addWidget(self.verificado)
        linha.addStretch(1)
        l.addLayout(linha)

        self.tipo_nota = QLabel("")
        self.tipo_nota.setWordWrap(True)
        self.tipo_nota.setStyleSheet(theme.CSS_DIM)
        l.addWidget(self.tipo_nota)
        l.addStretch(1)
        return w

    def _aba_conexao(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        g = GradeCampos(3)
        self.interface = QComboBox()
        self.interface.addItems(INTERFACES)
        self.interface.currentIndexChanged.connect(self._recalcular_visa)
        g.add("Interface", self.interface,
               "Passivo (cabo, atenuador) não tem endereço: use 'nenhuma'.")
        self.placa = QSpinBox(); self.placa.setRange(0, 15)
        self.placa.valueChanged.connect(self._recalcular_visa)
        g.add("Placa", self.placa, "No laboratório só existe a placa GPIB0.")
        self.endereco = QSpinBox(); self.endereco.setRange(0, 30)
        self.endereco.valueChanged.connect(self._recalcular_visa)
        g.add("Endereço", self.endereco)
        self.host = QLineEdit()
        self.host.textChanged.connect(self._recalcular_visa)
        g.add("Host (TCPIP)", self.host, span=2)
        self.porta_serial = QSpinBox(); self.porta_serial.setRange(1, 64)
        self.porta_serial.valueChanged.connect(self._recalcular_visa)
        g.add("Porta serial", self.porta_serial, "3 → COM3 (ASRL3::INSTR)")
        self.timeout = QSpinBox()
        self.timeout.setRange(1000, 300000); self.timeout.setSingleStep(1000)
        self.timeout.setSuffix(" ms")
        g.add("Timeout", self.timeout)
        self.visa = QLineEdit(); self.visa.setReadOnly(True)
        self.visa.setFont(theme.mono_font(9))
        g.add("Recurso VISA", self.visa,
               "Montado a partir dos campos acima.", span=2)
        l.addWidget(g)
        nota = QLabel(
            "GPIB exige NI-VISA ou R&S VISA instalado — o pyvisa-py puro não "
            "fala GPIB, só LAN, USB e serial.")
        nota.setWordWrap(True)
        nota.setStyleSheet(theme.CSS_DIM)
        l.addWidget(nota)
        l.addStretch(1)
        return w

    def _aba_comandos(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        ajuda = QLabel(
            "Chave <b>ausente</b> herda o padrão SCPI. Chave <b>vazia</b> "
            "significa que este modelo não tem o comando — e nada é enviado. "
            "São coisas diferentes de propósito.")
        ajuda.setWordWrap(True)
        ajuda.setStyleSheet(theme.CSS_MUTED)
        l.addWidget(ajuda)
        self.tabela_cmd = QTableWidget(0, 2)
        self.tabela_cmd.setHorizontalHeaderLabels(["Chave", "Comando SCPI"])
        self.tabela_cmd.setAlternatingRowColors(True)
        self.tabela_cmd.verticalHeader().setDefaultSectionSize(24)
        self.tabela_cmd.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tabela_cmd.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        l.addWidget(self.tabela_cmd, 1)
        linha = QHBoxLayout()
        for texto, slot in (("Adicionar comando", self._add_cmd),
                             ("Remover", self._del_cmd),
                             ("Trazer padrão SCPI", self._cmd_padrao)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            linha.addWidget(b)
        linha.addStretch(1)
        l.addLayout(linha)
        return w

    def _aba_certificados(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Certificado:"))
        self.cert_combo = QComboBox()
        self.cert_combo.currentIndexChanged.connect(self._carregar_certificado)
        topo.addWidget(self.cert_combo, 1)
        for texto, slot in (("Novo", self._novo_cert), ("Excluir", self._del_cert)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            topo.addWidget(b)
        l.addLayout(topo)

        g = GradeCampos(3)
        self.cert_num = QLineEdit();  g.add("Número", self.cert_num)
        self.cert_lab = QLineEdit();  g.add("Laboratório", self.cert_lab, span=2)
        self.cert_data = QDateEdit(); self.cert_data.setCalendarPopup(True)
        self.cert_data.setDisplayFormat("dd/MM/yyyy")
        g.add("Calibração", self.cert_data)
        self.cert_val = QDateEdit(); self.cert_val.setCalendarPopup(True)
        self.cert_val.setDisplayFormat("dd/MM/yyyy")
        g.add("Validade", self.cert_val)
        self.cert_k = QDoubleSpinBox(); self.cert_k.setRange(1.0, 5.0)
        self.cert_k.setSingleStep(0.1); self.cert_k.setValue(2.0)
        g.add("Fator k", self.cert_k)
        self.cert_grandeza = QLineEdit()
        g.add("Grandeza", self.cert_grandeza, span=3)
        l.addWidget(g)

        nota = QLabel(
            "Entre os pontos o valor é interpolado em log da frequência; fora "
            "da faixa calibrada mantém-se o valor da extremidade (não há "
            "extrapolação).")
        nota.setWordWrap(True)
        nota.setStyleSheet(theme.CSS_DIM)
        l.addWidget(nota)

        self.tabela_pts = QTableWidget(0, len(PONTO_COLS))
        self.tabela_pts.setHorizontalHeaderLabels(PONTO_COLS)
        self.tabela_pts.setAlternatingRowColors(True)
        self.tabela_pts.verticalHeader().setDefaultSectionSize(24)
        self.tabela_pts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabela_pts.setMinimumHeight(140)
        l.addWidget(self.tabela_pts, 1)
        linha = QHBoxLayout()
        for texto, slot in (("Adicionar ponto", self._add_ponto),
                             ("Remover ponto", self._del_ponto),
                             ("Importar CSV…", self._importar_csv)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            linha.addWidget(b)
        linha.addStretch(1)
        l.addLayout(linha)
        return w

    def _aba_notas(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        ajuda = QLabel(
            "O que se aprendeu usando este aparelho: comando que não funciona, "
            "erro que ele devolve, ordem que importa. É o conhecimento que "
            "some quando quem sabia sai do laboratório.")
        ajuda.setWordWrap(True)
        ajuda.setStyleSheet(theme.CSS_MUTED)
        l.addWidget(ajuda)
        self.notas = QPlainTextEdit()
        l.addWidget(self.notas, 1)
        return w

    # ------------------------------------------------------------ arvore
    def _montar_arvore(self):
        alvo = (self.filtro.text() or "").strip().lower()
        atual_id = self.atual.id if self.atual else None
        self.arvore.blockSignals(True)
        self.arvore.clear()
        lista = todos()
        n_mostrados = 0
        por_tipo: dict[str, list[Dispositivo]] = {}
        for d in lista:
            if alvo and alvo not in " ".join(
                    (d.fabricante, d.modelo, d.numero_serie, d.patrimonio,
                     d.descricao, d.id)).lower():
                continue
            por_tipo.setdefault(d.tipo, []).append(d)
            n_mostrados += 1

        for grupo in GRUPOS:
            tipos_com_algo = [t for t in tipos_do_grupo(grupo) if por_tipo.get(t.id)]
            if not tipos_com_algo:
                continue
            no_grupo = QTreeWidgetItem([grupo.upper()])
            no_grupo.setFlags(Qt.ItemIsEnabled)
            f = no_grupo.font(0); f.setBold(True); f.setPointSize(f.pointSize() - 1)
            no_grupo.setFont(0, f)
            no_grupo.setForeground(0, theme.status_color(""))
            self.arvore.addTopLevelItem(no_grupo)
            for t in tipos_com_algo:
                ds = sorted(por_tipo[t.id], key=lambda x: x.rotulo().lower())
                no_tipo = QTreeWidgetItem([f"{t.nome}  ({len(ds)})"])
                no_tipo.setFlags(Qt.ItemIsEnabled)
                no_grupo.addChild(no_tipo)
                for d in ds:
                    it = QTreeWidgetItem([d.rotulo()])
                    it.setData(0, Qt.UserRole, d.id)
                    sit = d.situacao()
                    if sit == "vencido":
                        it.setForeground(0, theme.status_color("REPROVADO"))
                    elif sit == "vence_em_breve":
                        it.setForeground(0, theme.status_color("INDET"))
                    if not d.ativo:
                        it.setForeground(0, theme.status_color(""))
                    it.setToolTip(0, f"{TEXTO_SITUACAO[sit]}"
                                      + (f" · {len(d.comandos)} comandos" if d.comandos else ""))
                    no_tipo.addChild(it)
            no_grupo.setExpanded(True)
        self.arvore.blockSignals(False)
        self.contagem.setText(f"{n_mostrados} de {len(lista)}")
        if atual_id:
            self._selecionar_id(atual_id)

    def _selecionar_id(self, disp_id: str):
        it = self.arvore.findItems(
            "", Qt.MatchContains | Qt.MatchRecursive, 0)
        for i in it:
            if i.data(0, Qt.UserRole) == disp_id:
                self.arvore.setCurrentItem(i)
                return

    def _ao_selecionar(self, atual, _anterior):
        disp_id = atual.data(0, Qt.UserRole) if atual else None
        if not disp_id:
            return
        try:
            self.atual = carregar(caminho(disp_id))
        except Exception as e:
            QMessageBox.warning(self, "Erro ao abrir", str(e))
            return
        self._preencher()
        self._habilitar(True)

    # ------------------------------------------------------------ ficha
    def _preencher(self):
        d = self.atual
        self.rotulo.setText(d.rotulo())
        sit = d.situacao()
        self.badge_situacao.setText(TEXTO_SITUACAO[sit])
        self.badge_situacao.set_cor(COR_SITUACAO[sit])
        self.badge_verificado.setText("VALIDADO" if d.verificado else "NÃO VALIDADO")
        self.badge_verificado.set_cor("verde" if d.verificado else "ambar")

        i = self.tipo_combo.findData(d.tipo)
        self.tipo_combo.blockSignals(True)
        self.tipo_combo.setCurrentIndex(i if i >= 0 else 0)
        self.tipo_combo.blockSignals(False)
        self._mostrar_nota_tipo()

        self.fabricante.setText(d.fabricante)
        self.modelo.setText(d.modelo)
        self.serie.setText(d.numero_serie)
        self.patrimonio.setText(d.patrimonio)
        self.descricao.setText(d.descricao)
        self.aplicar.setCurrentText(d.aplicar)
        self.ativo.setChecked(d.ativo)
        self.verificado.setChecked(d.verificado)

        c = d.conexao
        self.interface.setCurrentText(c.interface)
        self.placa.setValue(c.placa)
        self.endereco.setValue(c.endereco)
        self.host.setText(c.host)
        self.porta_serial.setValue(c.porta_serial)
        self.timeout.setValue(c.timeout_ms)
        self._recalcular_visa()

        self.tabela_cmd.setRowCount(0)
        for chave, cmd in sorted(d.comandos.items()):
            r = self.tabela_cmd.rowCount()
            self.tabela_cmd.insertRow(r)
            self.tabela_cmd.setItem(r, 0, QTableWidgetItem(chave))
            self.tabela_cmd.setItem(r, 1, QTableWidgetItem(cmd))

        self.notas.setPlainText(d.notas)
        self._recarregar_certificados()

    def _mostrar_nota_tipo(self):
        t = TIPOS.get(self.tipo_combo.currentData())
        if not t:
            self.tipo_nota.setText("")
            return
        partes = []
        partes.append("Costuma ter comandos." if t.comandos else "Normalmente passivo (sem comandos).")
        partes.append("Costuma ter correção." if t.correcao else "Normalmente sem correção.")
        if t.nota:
            partes.append(t.nota)
        self.tipo_nota.setText("  ·  ".join(partes))

    def _ao_trocar_tipo(self):
        self._mostrar_nota_tipo()

    def _recalcular_visa(self):
        c = Conexao(interface=self.interface.currentText(),
                     placa=self.placa.value(), endereco=self.endereco.value(),
                     host=self.host.text(), porta_serial=self.porta_serial.value())
        self.visa.setText(c.recurso_visa() or "— passivo, sem endereço —")

    def _habilitar(self, on: bool):
        self.abas.setEnabled(on)
        if not on:
            self.rotulo.setText("Nenhum dispositivo selecionado")

    # --------------------------------------------------------- comandos
    def _add_cmd(self):
        chave, ok = QInputDialog.getText(self, "Novo comando", "Chave (ex.: freq_start):")
        if not ok or not chave.strip():
            return
        r = self.tabela_cmd.rowCount()
        self.tabela_cmd.insertRow(r)
        self.tabela_cmd.setItem(r, 0, QTableWidgetItem(chave.strip()))
        self.tabela_cmd.setItem(r, 1, QTableWidgetItem(""))

    def _del_cmd(self):
        r = self.tabela_cmd.currentRow()
        if r >= 0:
            self.tabela_cmd.removeRow(r)

    def _cmd_padrao(self):
        from instruments.receiver_models import BASE_COMMANDS
        existentes = {self.tabela_cmd.item(r, 0).text()
                      for r in range(self.tabela_cmd.rowCount())
                      if self.tabela_cmd.item(r, 0)}
        n = 0
        for chave, cmd in sorted(BASE_COMMANDS.items()):
            if chave in existentes:
                continue
            r = self.tabela_cmd.rowCount()
            self.tabela_cmd.insertRow(r)
            self.tabela_cmd.setItem(r, 0, QTableWidgetItem(chave))
            self.tabela_cmd.setItem(r, 1, QTableWidgetItem(cmd))
            n += 1
        self.aviso.setText(f"{n} comando(s) do padrão SCPI acrescentado(s).")

    # ------------------------------------------------------ certificados
    def _recarregar_certificados(self):
        self.cert_combo.blockSignals(True)
        self.cert_combo.clear()
        for i, c in enumerate(self.atual.certificados):
            self.cert_combo.addItem(f"{c.numero or '(sem número)'} — {c.data_calibracao}", i)
        self.cert_combo.blockSignals(False)
        if self.atual.certificados:
            self.cert_combo.setCurrentIndex(0)
            self._carregar_certificado()
        else:
            self._limpar_certificado()

    def _limpar_certificado(self):
        self.cert_num.clear(); self.cert_lab.clear(); self.cert_grandeza.clear()
        self.cert_k.setValue(2.0)
        self.tabela_pts.setRowCount(0)

    def _cert_atual(self) -> Certificado | None:
        i = self.cert_combo.currentIndex()
        if i < 0 or i >= len(self.atual.certificados):
            return None
        return self.atual.certificados[i]

    def _carregar_certificado(self):
        c = self._cert_atual()
        if c is None:
            self._limpar_certificado(); return
        self.cert_num.setText(c.numero)
        self.cert_lab.setText(c.laboratorio)
        self.cert_grandeza.setText(c.grandeza)
        self.cert_k.setValue(c.fator_k)
        for campo, valor in ((self.cert_data, c.data_calibracao),
                              (self.cert_val, c.data_validade)):
            d = QDate.fromString(valor or "", "yyyy-MM-dd")
            campo.setDate(d if d.isValid() else QDate.currentDate())
        self.tabela_pts.setRowCount(0)
        for p in c.pontos:
            r = self.tabela_pts.rowCount()
            self.tabela_pts.insertRow(r)
            for col, v in enumerate((p.freq_hz, p.valor_db, p.incerteza_db)):
                self.tabela_pts.setItem(r, col, QTableWidgetItem(f"{v:g}"))

    def _novo_cert(self):
        self.atual.certificados.append(Certificado(
            numero="", laboratorio="",
            data_calibracao=date.today().isoformat(),
            data_validade=date.today().replace(year=date.today().year + 1).isoformat(),
            fator_k=2.0, grandeza="", pontos=[]))
        self._recarregar_certificados()
        self.cert_combo.setCurrentIndex(len(self.atual.certificados) - 1)

    def _del_cert(self):
        i = self.cert_combo.currentIndex()
        if i < 0:
            return
        del self.atual.certificados[i]
        self._recarregar_certificados()

    def _add_ponto(self):
        r = self.tabela_pts.rowCount()
        self.tabela_pts.insertRow(r)
        for col, v in enumerate(("1000000", "0", "0")):
            self.tabela_pts.setItem(r, col, QTableWidgetItem(v))

    def _del_ponto(self):
        r = self.tabela_pts.currentRow()
        if r >= 0:
            self.tabela_pts.removeRow(r)

    def _importar_csv(self):
        caminho_csv, _ = QFileDialog.getOpenFileName(
            self, "Importar pontos do certificado", "", "CSV (*.csv *.txt);;Todos (*.*)")
        if not caminho_csv:
            return
        import csv
        lidos = 0
        self.tabela_pts.setRowCount(0)
        try:
            with open(caminho_csv, newline="", encoding="utf-8-sig") as f:
                for linha in csv.reader(f, delimiter=None if False else ","):
                    if len(linha) < 2:
                        continue
                    try:
                        vals = [float(str(x).replace(",", ".")) for x in linha[:3]]
                    except ValueError:
                        continue   # cabeçalho
                    while len(vals) < 3:
                        vals.append(0.0)
                    r = self.tabela_pts.rowCount()
                    self.tabela_pts.insertRow(r)
                    for col, v in enumerate(vals):
                        self.tabela_pts.setItem(r, col, QTableWidgetItem(f"{v:g}"))
                    lidos += 1
        except OSError as e:
            QMessageBox.warning(self, "Erro ao ler", str(e)); return
        self.aviso.setText(f"{lidos} ponto(s) importado(s). Salve para gravar.")

    # ------------------------------------------------------------ CRUD
    def _coletar(self) -> Dispositivo:
        d = self.atual
        d.tipo = self.tipo_combo.currentData()
        d.fabricante = self.fabricante.text().strip()
        d.modelo = self.modelo.text().strip()
        d.numero_serie = self.serie.text().strip()
        d.patrimonio = self.patrimonio.text().strip()
        d.descricao = self.descricao.text().strip()
        d.aplicar = self.aplicar.currentText()
        d.ativo = self.ativo.isChecked()
        d.verificado = self.verificado.isChecked()
        d.notas = self.notas.toPlainText()
        d.conexao = Conexao(
            interface=self.interface.currentText(), placa=self.placa.value(),
            endereco=self.endereco.value(), host=self.host.text().strip(),
            porta_serial=self.porta_serial.value(), timeout_ms=self.timeout.value())
        d.comandos = {}
        for r in range(self.tabela_cmd.rowCount()):
            k = self.tabela_cmd.item(r, 0)
            v = self.tabela_cmd.item(r, 1)
            if k and k.text().strip():
                d.comandos[k.text().strip()] = v.text().strip() if v else ""
        c = self._cert_atual()
        if c is not None:
            c.numero = self.cert_num.text().strip()
            c.laboratorio = self.cert_lab.text().strip()
            c.grandeza = self.cert_grandeza.text().strip()
            c.fator_k = self.cert_k.value()
            c.data_calibracao = self.cert_data.date().toString("yyyy-MM-dd")
            c.data_validade = self.cert_val.date().toString("yyyy-MM-dd")
            pontos = []
            for r in range(self.tabela_pts.rowCount()):
                try:
                    vals = [float(self.tabela_pts.item(r, col).text().replace(",", "."))
                            for col in range(3)]
                except (AttributeError, ValueError):
                    continue
                pontos.append(PontoCertificado(freq_hz=vals[0], valor_db=vals[1],
                                                incerteza_db=vals[2]))
            c.pontos = sorted(pontos, key=lambda p: p.freq_hz)
        return d

    def _salvar(self):
        if self.atual is None:
            return
        d = self._coletar()
        salvar(d)
        self._montar_arvore()
        self._preencher()
        self.aviso.setText(f"Salvo em dados/dispositivos/{d.id}.json")
        self.catalogo_mudou.emit()

    def _novo(self):
        disp_id, ok = QInputDialog.getText(
            self, "Novo dispositivo",
            "Identificador (sem espaços, ex.: env216_2):")
        if not ok or not disp_id.strip():
            return
        d = Dispositivo(id=disp_id.strip(), tipo=self.tipo_combo.currentData() or "cable")
        salvar(d)
        self.atual = d
        self._montar_arvore()
        self._selecionar_id(d.id)
        self.catalogo_mudou.emit()

    def _duplicar(self):
        if self.atual is None:
            return
        novo_id, ok = QInputDialog.getText(
            self, "Duplicar", "Identificador do novo:", text=f"{self.atual.id}_copia")
        if not ok or not novo_id.strip():
            return
        import copy
        d = copy.deepcopy(self.atual)
        d.id = novo_id.strip()
        d.numero_serie = ""
        d.patrimonio = ""
        salvar(d)
        self._montar_arvore()
        self._selecionar_id(d.id)
        self.catalogo_mudou.emit()

    def _excluir(self):
        if self.atual is None:
            return
        r = QMessageBox.question(
            self, "Excluir dispositivo",
            f"Excluir «{self.atual.rotulo()}» em definitivo?\n\n"
            "Os certificados registrados nele vão junto.")
        if r != QMessageBox.Yes:
            return
        excluir(self.atual.id)
        self.atual = None
        self._habilitar(False)
        self._montar_arvore()
        self.catalogo_mudou.emit()
