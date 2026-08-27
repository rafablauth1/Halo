"""
gui/corrections_manager.py

Gerenciador de tabelas de correcao (fator de LISN, fator de antena,
perda de cabo etc.), no mesmo espirito das tabelas de correcao do
RadiMation: uma lista de pontos (frequencia, dB) por tabela, criada,
editada, importada de CSV, duplicada, renomeada e excluida pela GUI.
Nada fixo no codigo -- tudo persiste em core/corrections_lib/*.json e
fica disponivel para aplicar a qualquer trace na tela principal.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QMessageBox,
                                QInputDialog, QLineEdit, QFormLayout, QTableWidget,
                                QTableWidgetItem, QFileDialog, QSplitter, QWidget)
from PySide6.QtCore import Qt

from core.corrections import (CorrectionTable, list_available_corrections, load_correction,
                               save_correction, new_correction, duplicate_correction,
                               rename_correction, delete_correction)


class CorrectionsManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar tabelas de correcao")
        self.resize(760, 480)
        self.changed = False
        self.current_path: Path | None = None

        layout = QVBoxLayout(self)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("Tabelas salvas:"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        left_l.addWidget(self.list)
        list_btn_row = QHBoxLayout()
        new_btn = QPushButton("Nova")
        new_btn.clicked.connect(self._new)
        dup_btn = QPushButton("Duplicar")
        dup_btn.clicked.connect(self._duplicate)
        del_btn = QPushButton("Excluir")
        del_btn.clicked.connect(self._delete)
        list_btn_row.addWidget(new_btn)
        list_btn_row.addWidget(dup_btn)
        list_btn_row.addWidget(del_btn)
        left_l.addLayout(list_btn_row)
        import_btn = QPushButton("Importar CSV...")
        import_btn.clicked.connect(self._import_csv)
        left_l.addWidget(import_btn)
        splitter.addWidget(left)

        right = QWidget()
        right_l = QVBoxLayout(right)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Nome", self.name_edit)
        self.unit_note_edit = QLineEdit()
        form.addRow("Observacao/unidade", self.unit_note_edit)
        right_l.addLayout(form)

        right_l.addWidget(QLabel("Pontos (frequencia Hz, correcao dB) - interpolado em log(f):"))
        self.points_table = QTableWidget(0, 2)
        self.points_table.setHorizontalHeaderLabels(["Frequencia (Hz)", "Correcao (dB)"])
        right_l.addWidget(self.points_table)

        pts_btn_row = QHBoxLayout()
        add_pt_btn = QPushButton("Adicionar ponto")
        add_pt_btn.clicked.connect(self._add_point)
        del_pt_btn = QPushButton("Remover ponto")
        del_pt_btn.clicked.connect(self._del_point)
        pts_btn_row.addWidget(add_pt_btn)
        pts_btn_row.addWidget(del_pt_btn)
        pts_btn_row.addStretch(1)
        right_l.addLayout(pts_btn_row)

        save_btn = QPushButton("Salvar tabela")
        save_btn.clicked.connect(self._save)
        right_l.addWidget(save_btn)
        splitter.addWidget(right)
        splitter.setSizes([220, 540])

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._set_editor_enabled(False)
        self._refresh()

    def _set_editor_enabled(self, enabled: bool):
        for w in (self.name_edit, self.unit_note_edit, self.points_table):
            w.setEnabled(enabled)

    def _refresh(self, select_path: Path | None = None):
        self.list.clear()
        for p in list_available_corrections():
            item = QListWidgetItem(p.stem)
            item.setData(Qt.UserRole, str(p))
            self.list.addItem(item)
            if select_path is not None and p == select_path:
                self.list.setCurrentItem(item)
        if self.list.count() == 0:
            self.current_path = None
            self.name_edit.clear()
            self.unit_note_edit.clear()
            self.points_table.setRowCount(0)
            self._set_editor_enabled(False)

    def _on_select(self, item: QListWidgetItem | None):
        if item is None:
            return
        self.current_path = Path(item.data(Qt.UserRole))
        table = load_correction(self.current_path)
        self._set_editor_enabled(True)
        self.name_edit.setText(table.name)
        self.unit_note_edit.setText(table.unit_note)
        self.points_table.setRowCount(0)
        for f, c in table.points:
            row = self.points_table.rowCount()
            self.points_table.insertRow(row)
            self.points_table.setItem(row, 0, QTableWidgetItem(str(f)))
            self.points_table.setItem(row, 1, QTableWidgetItem(str(c)))

    def _add_point(self):
        row = self.points_table.rowCount()
        self.points_table.insertRow(row)
        self.points_table.setItem(row, 0, QTableWidgetItem("0"))
        self.points_table.setItem(row, 1, QTableWidgetItem("0"))

    def _del_point(self):
        rows = sorted({i.row() for i in self.points_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.points_table.removeRow(r)

    def _new(self):
        name, ok = QInputDialog.getText(self, "Nova tabela de correcao", "Nome:")
        if not ok or not name.strip():
            return
        try:
            path = new_correction(name)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)

    def _duplicate(self):
        if self.current_path is None:
            QMessageBox.information(self, "Selecione", "Selecione uma tabela para duplicar.")
            return
        base_name = self.current_path.stem
        name, ok = QInputDialog.getText(self, "Duplicar tabela", "Nome da copia:", text=f"{base_name}_copia")
        if not ok or not name.strip():
            return
        try:
            path = duplicate_correction(self.current_path, name)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)

    def _delete(self):
        if self.current_path is None:
            QMessageBox.information(self, "Selecione", "Selecione uma tabela para excluir.")
            return
        if QMessageBox.question(self, "Confirmar exclusao",
                                 f"Excluir permanentemente '{self.current_path.stem}'?") != QMessageBox.Yes:
            return
        delete_correction(self.current_path)
        self.changed = True
        self._refresh()

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar CSV de correcao", "",
                                               "CSV (*.csv *.txt);;Todos (*.*)")
        if not path:
            return
        try:
            table = CorrectionTable.from_csv(path)
        except Exception as e:
            QMessageBox.warning(self, "Erro ao importar", str(e))
            return
        name, ok = QInputDialog.getText(self, "Nome da tabela importada", "Nome:", text=table.name)
        if not ok or not name.strip():
            return
        table.name = name.strip()
        try:
            dst = new_correction(name)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        save_correction(table, dst)
        self.changed = True
        self._refresh(select_path=dst)

    def _save(self):
        if self.current_path is None:
            return
        try:
            points = []
            for row in range(self.points_table.rowCount()):
                f = float(self.points_table.item(row, 0).text())
                c = float(self.points_table.item(row, 1).text())
                points.append((f, c))
        except (ValueError, AttributeError) as e:
            QMessageBox.warning(self, "Erro", f"Valor invalido em algum ponto: {e}")
            return
        points.sort(key=lambda p: p[0])

        new_name = self.name_edit.text().strip()
        table = CorrectionTable(name=new_name or self.current_path.stem,
                                 unit_note=self.unit_note_edit.text(), points=points)
        try:
            if new_name and new_name != self.current_path.stem:
                dst = rename_correction(self.current_path, new_name)
                self.current_path = dst
            save_correction(table, self.current_path)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        QMessageBox.information(self, "Salvo", f"Tabela salva em {self.current_path.name}")
        self._refresh(select_path=self.current_path)
