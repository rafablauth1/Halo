from dataclasses import dataclass, field

from emc.config import (
    DEFAULT_CHROMA_CONNECTION,
    DEFAULT_COUNTER_CONNECTION,
    DEFAULT_GPIB_ADDRESSES,
    DEFAULT_GPIB_BOARDS,
    DEFAULT_SERIAL_PORTS,
    DEFAULT_UCS500N_CONNECTION,
    SIMULATION_MODE,
)


@dataclass
class RuntimeSettings:
    simulation_mode: bool = SIMULATION_MODE
    gpib_addresses: dict = field(default_factory=lambda: dict(DEFAULT_GPIB_ADDRESSES))
    gpib_boards: dict = field(default_factory=lambda: dict(DEFAULT_GPIB_BOARDS))
    serial_ports: dict = field(default_factory=lambda: dict(DEFAULT_SERIAL_PORTS))
    ucs500n_connection: str = DEFAULT_UCS500N_CONNECTION
    chroma_connection: str = DEFAULT_CHROMA_CONNECTION
    counter_connection: str = DEFAULT_COUNTER_CONNECTION
    buzzer_enabled: bool = True


settings = RuntimeSettings()
