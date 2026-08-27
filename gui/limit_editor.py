"""
gui/limit_editor.py

Editor completo de uma norma/metodo (StandardMethod): metadados (titulo,
referencia da norma, faixa de frequencia, tipo de eixo, notas) + a tabela
de segmentos de limite. Cada linha da tabela define seu proprio detector,
unidade e tipo de interpolacao -- ou seja, o usuario pode criar QUALQUER
detector/linha de limite novo (nao so editar os que ja existiam), no mesmo
espirito dos arquivos .lim do RadiMation: nada aqui e fixo no codigo, tudo
e configuravel pela GUI e persistido em core/standards/*.json.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                                QTableWidgetItem, QPushButton, QLabel, QComboBox,
                                QMessageBox, QFormLayout, QLineEdit, QDoubleSpinBox,
                                QTextEdit, QGroupBox)
from PySide6.QtCore import Qt

from core.limits import StandardMethod, LimitLine, LimitSegment, save_method

COLS = ["Detector", "Unidade", "Interpolacao", "Freq inicio (Hz)", "Freq fim (Hz)",
        "Valor inicio", "Valor fim", "Verificado", "Nota"]
INTERPOLATIONS = ["log-linear", "linear", "log-log"]


class LimitEditorDialog(QDialog):
    def __init__(self, method: StandardMethod, json_path: Path, parent=None):
        super().__init__(parent)
        self.method = method
        self.json_path = json_path
        self.setWindowTitle(f"Editor de norma - {method.title}")
        self.resize(1040, 620)

        layout = QVBoxLayout(self)

        meta_box = QGroupBox("Dados da norma/metodo")
        meta_l = QFormLayout(meta_box)
        self.title_edit = QLineEdit(method.title)
        meta_l.addRow("Titulo", self.title_edit)
        self.ref_edit = QLineEdit(method.standard_ref)
        meta_l.addRow("Referencia da norma", self.ref_edit)

        freq_row = QHBoxLayout()
        self.fmin_spin = QDoubleSpinBox()
        self.fmin_spin.setRange(0, 1e12)
        self.fmin_spin.setDecimals(0)
        self.fmin_spin.setValue(method.freq_range_hz[0])
        self.fmax_spin = QDoubleSpinBox()
        self.fmax_spin.setRange(0, 1e12)
        self.fmax_spin.setDecimals(0)
        self.fmax_spin.setValue(method.freq_range_hz[1])
        freq_row.addWidget(QLabel("de (Hz)"))
        freq_row.addWidget(self.fmin_spin)
        freq_row.addWidget(QLabel("ate (Hz)"))
        freq_row.addWidget(self.fmax_spin)
        meta_l.addRow("Faixa de frequencia", freq_row)

        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["log", "linear"])
        self.axis_combo.setCurrentText(method.x_axis if method.x_axis in ("log", "linear") else "log")
        meta_l.addRow("Eixo X do grafico", self.axis_combo)

        self.notes_edit = QTextEdit(method.notes)
        self.notes_edit.setMaximumHeight(60)
        meta_l.addRow("Notas", self.notes_edit)
        layout.addWidget(meta_box)

        layout.addWidget(QLabel("Segmentos de limite (uma linha = um trecho de frequencia de um detector; "
                                 "para criar um detector/linha de limite novo, basta digitar um nome novo "
                                 "na coluna Detector de uma linha adicionada)"))

        self.table = QTableWidget(0, len(COLS))
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setHorizontalHeaderLabels(COLS)
        layout.addWidget(self.table)
        self._populate()

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Adicionar segmento")
        add_btn.clicked.connect(self._add_row)
        dup_btn = QPushButton("Duplicar selecionado")
        dup_btn.clicked.connect(self._dup_row)
        del_btn = QPushButton("Remover selecionado")
        del_btn.clicked.connect(self._del_row)
        save_btn = QPushButton("Salvar")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(dup_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _set_row(self, row: int, detector: str, unit: str, interpolation: str,
                 f0: str, f1: str, v0: str, v1: str, verified: str, note: str):
        self.table.setItem(row, 0, QTableWidgetItem(detector))
        self.table.setItem(row, 1, QTableWidgetItem(unit))
        interp_combo = QComboBox()
        interp_combo.addItems(INTERPOLATIONS)
        interp_combo.setCurrentText(interpolation if interpolation in INTERPOLATIONS else "log-linear")
        self.table.setCellWidget(row, 2, interp_combo)
        self.table.setItem(row, 3, QTableWidgetItem(f0))
        self.table.setItem(row, 4, QTableWidgetItem(f1))
        self.table.setItem(row, 5, QTableWidgetItem(v0))
        self.table.setItem(row, 6, QTableWidgetItem(v1))
        self.table.setItem(row, 7, QTableWidgetItem(verified))
        self.table.setItem(row, 8, QTableWidgetItem(note))

    def _populate(self):
        self.table.setRowCount(0)
        for ll in self.method.limit_lines:
            for seg in ll.segments:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._set_row(
                    row, ll.detector, ll.unit, ll.interpolation,
                    str(seg.freq_start_hz), str(seg.freq_end_hz),
                    "" if seg.value_start is None else str(seg.value_start),
                    "" if seg.value_end is None else str(seg.value_end),
                    "sim" if seg.verified else "nao", seg.note,
                )

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_row(row, "NOVO_DETECTOR", "dBuV", "log-linear", "0", "0", "", "", "nao", "")

    def _dup_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            interp_widget = self.table.cellWidget(r, 2)
            interp = interp_widget.currentText() if interp_widget else "log-linear"
            vals = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in (0, 1)]
            vals2 = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in (3, 4, 5, 6, 7, 8)]
            self._set_row(row, vals[0], vals[1], interp, *vals2)

    def _del_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _save(self):
        by_detector: dict[str, list[LimitSegment]] = {}
        line_meta: dict[str, tuple[str, str]] = {}  # detector -> (unit, interpolation)
        try:
            for row in range(self.table.rowCount()):
                det = self.table.item(row, 0).text().strip()
                if not det:
                    raise ValueError(f"Linha {row + 1}: detector nao pode ser vazio.")
                unit = self.table.item(row, 1).text().strip() or "dBuV"
                interp_widget = self.table.cellWidget(row, 2)
                interp = interp_widget.currentText() if interp_widget else "log-linear"
                f0 = float(self.table.item(row, 3).text())
                f1 = float(self.table.item(row, 4).text())
                v0_txt = self.table.item(row, 5).text().strip()
                v1_txt = self.table.item(row, 6).text().strip()
                v0 = float(v0_txt) if v0_txt else None
                v1 = float(v1_txt) if v1_txt else None
                verified = self.table.item(row, 7).text().strip().lower() in ("sim", "true", "1")
                note = self.table.item(row, 8).text()
                by_detector.setdefault(det, []).append(LimitSegment(f0, f1, v0, v1, verified=verified, note=note))
                line_meta.setdefault(det, (unit, interp))
        except (ValueError, AttributeError) as e:
            QMessageBox.warning(self, "Erro", f"Valor invalido em alguma celula: {e}")
            return

        if self.fmax_spin.value() <= self.fmin_spin.value():
            QMessageBox.warning(self, "Erro", "Frequencia final da norma deve ser maior que a inicial.")
            return

        self.method.title = self.title_edit.text().strip() or self.method.id
        self.method.standard_ref = self.ref_edit.text().strip()
        self.method.freq_range_hz = (self.fmin_spin.value(), self.fmax_spin.value())
        self.method.x_axis = self.axis_combo.currentText()
        self.method.notes = self.notes_edit.toPlainText()

        new_lines = []
        for det, segs in by_detector.items():
            unit, interp = line_meta[det]
            new_lines.append(LimitLine(
                name=det, detector=det, unit=unit, interpolation=interp,
                segments=sorted(segs, key=lambda s: s.freq_start_hz),
            ))
        self.method.limit_lines = new_lines

        save_method(self.method, self.json_path)
        QMessageBox.information(self, "Salvo", f"Norma salva em {self.json_path.name}")
        self.accept()
