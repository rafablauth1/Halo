"""HALO — ensaios de emissao CISPR 15. Rode com: python main.py"""
import sys

from PySide6.QtWidgets import QApplication

from gui import theme
from gui.main_window import MainWindow


def _identidade_windows():
    """Faz a barra de tarefas do Windows mostrar o icone do HALO.

    Sem um AppUserModelID proprio, o Windows agrupa a janela sob o icone
    do python.exe/pythonw.exe que a iniciou -- e o atalho da area de
    trabalho aparece com o icone certo, mas a janela aberta nao."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "halo.cispr15.app")
    except Exception:
        pass   # cosmetico: se falhar, o programa roda igual


def main():
    _identidade_windows()
    app = QApplication(sys.argv)
    theme.apply_theme(app)   # paleta, fonte, icone e folha de estilo
    from gui.paleta_dialog import aplicar_salvas
    aplicar_salvas(app)      # cores personalizadas, se houver
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
