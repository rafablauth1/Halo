"""
gui/standards_manager.py

Gerenciador de normas/metodos de ensaio: criar do zero, duplicar,
renomear e excluir arquivos de core/standards/*.json pela GUI, sem
precisar editar JSON na mao. E daqui que se abre o editor completo
(gui/limit_editor.py) de uma norma selecionada.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QMessageBox,
                                QInputDialog)

from core.limits import (list_available_methods, load_method, new_method,
                          duplicate_method, rename_method, delete_method)
from gui.limit_editor import LimitEditorDialog


class StandardsManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar normas/metodos")
        self.resize(560, 420)
        self.changed = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Normas/metodos definidos (core/standards/*.json):"))

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._edit)
        layout.addWidget(self.list)
        self._refresh()

        btn_row = QHBoxLayout()
        new_btn = QPushButton("Nova...")
        new_btn.clicked.connect(self._new)
        dup_btn = QPushButton("Duplicar...")
        dup_btn.clicked.connect(self._duplicate)
        ren_btn = QPushButton("Renomear id...")
        ren_btn.clicked.connect(self._rename)
        del_btn = QPushButton("Excluir")
        del_btn.clicked.connect(self._delete)
        edit_btn = QPushButton("Editar...")
        edit_btn.clicked.connect(self._edit)
        for b in (new_btn, dup_btn, ren_btn, del_btn, edit_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _refresh(self, select_path: Path | None = None):
        self.list.clear()
        for p in list_available_methods():
            try:
                m = load_method(p)
                label = f"{m.id} - {m.title}"
            except Exception:
                label = p.stem
            item = QListWidgetItem(label)
            item.setData(1, str(p))
            self.list.addItem(item)
            if select_path is not None and p == select_path:
                self.list.setCurrentItem(item)

    def _selected_path(self) -> Path | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return Path(item.data(1))

    def _new(self):
        method_id, ok = QInputDialog.getText(self, "Nova norma", "Id da norma (ex.: minha_norma):")
        if not ok or not method_id.strip():
            return
        try:
            path = new_method(method_id)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)
        self._edit()

    def _duplicate(self):
        src = self._selected_path()
        if src is None:
            QMessageBox.information(self, "Selecione", "Selecione uma norma para duplicar.")
            return
        base = load_method(src)
        new_id, ok = QInputDialog.getText(self, "Duplicar norma", "Id da copia:", text=f"{base.id}_copia")
        if not ok or not new_id.strip():
            return
        try:
            path = duplicate_method(src, new_id)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)

    def _rename(self):
        src = self._selected_path()
        if src is None:
            QMessageBox.information(self, "Selecione", "Selecione uma norma para renomear.")
            return
        base = load_method(src)
        new_id, ok = QInputDialog.getText(self, "Renomear id da norma", "Novo id:", text=base.id)
        if not ok or not new_id.strip() or new_id.strip() == base.id:
            return
        try:
            path = rename_method(src, new_id)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)

    def _delete(self):
        src = self._selected_path()
        if src is None:
            QMessageBox.information(self, "Selecione", "Selecione uma norma para excluir.")
            return
        if QMessageBox.question(self, "Confirmar exclusao",
                                 f"Excluir permanentemente '{src.name}'?") != QMessageBox.Yes:
            return
        delete_method(src)
        self.changed = True
        self._refresh()

    def _edit(self):
        src = self._selected_path()
        if src is None:
            QMessageBox.information(self, "Selecione", "Selecione uma norma para editar.")
            return
        method = load_method(src)
        dlg = LimitEditorDialog(method, src, self)
        if dlg.exec():
            self.changed = True
            self._refresh(select_path=src)
