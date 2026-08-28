import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Transport(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def write(self, command: str) -> None: ...

    @abstractmethod
    def query(self, command: str) -> str: ...

    @abstractmethod
    def close(self) -> None: ...


class SimulatedTransport(Transport):
    """Transport que não fala com hardware nenhum — usado enquanto SIMULATION_MODE=True."""

    def __init__(self, name: str):
        self.name = name
        self._connected = False

    def connect(self) -> None:
        self._connected = True
        logger.info("[SIM %s] conectado", self.name)

    def write(self, command: str) -> None:
        if not self._connected:
            raise RuntimeError(f"{self.name}: transport não conectado")
        logger.info("[SIM %s] -> %s", self.name, command)

    def query(self, command: str) -> str:
        self.write(command)
        if command.strip().upper() in ("*IDN?", "IDN?"):
            return f"EM TEST,{self.name},SIM-000001,SIM-FW1.0"
        return "OK"

    def close(self) -> None:
        self._connected = False
        logger.info("[SIM %s] desconectado", self.name)


class VisaTransport(Transport):
    """Transport real via PyVISA (GPIB ou RS232). Import de pyvisa é tardio para não
    exigir NI-VISA instalado em máquinas que só rodam em modo simulado."""

    def __init__(self, name: str, resource_name: str, timeout_ms: int = 5000):
        self.name = name
        self.resource_name = resource_name
        self.timeout_ms = timeout_ms
        self._instrument = None

    def connect(self) -> None:
        import pyvisa

        rm = pyvisa.ResourceManager()
        self._instrument = rm.open_resource(self.resource_name)
        self._instrument.timeout = self.timeout_ms
        logger.info("[GPIB %s] conectado em %s", self.name, self.resource_name)

    def write(self, command: str) -> None:
        if self._instrument is None:
            raise RuntimeError(f"{self.name}: transport não conectado")
        self._instrument.write(command)

    def query(self, command: str) -> str:
        if self._instrument is None:
            raise RuntimeError(f"{self.name}: transport não conectado")
        return self._instrument.query(command)

    def close(self) -> None:
        if self._instrument is not None:
            self._instrument.close()
            self._instrument = None


def gpib_resource(address: int) -> str:
    return f"GPIB0::{address}::INSTR"


def serial_resource(port: str) -> str:
    return f"ASRL{port}::INSTR"
