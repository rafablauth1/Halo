from typing import Callable

from PySide6.QtCore import QThread, Signal

from emc.instruments.base import InstrumentDriver


class CommTestWorker(QThread):
    """Testa a comunicação com um instrumento (connect + *IDN?) em thread separada,
    pra não travar a tela enquanto espera resposta (ou timeout) do GPIB."""

    result = Signal(bool, str)  # sucesso, mensagem (IDN ou erro)

    def __init__(self, driver_factory: Callable[[], InstrumentDriver], parent=None):
        super().__init__(parent)
        self.driver_factory = driver_factory

    def run(self) -> None:
        driver = None
        try:
            driver = self.driver_factory()
            driver.connect()
            idn = driver.idn()
            self.result.emit(True, idn)
        except Exception as exc:
            self.result.emit(False, str(exc))
        finally:
            if driver is not None:
                try:
                    driver.disconnect()
                except Exception:
                    pass
