from emc.core.runtime_settings import settings
from emc.instruments.agilent_53131a import Agilent53131ACounter
from emc.instruments.chroma_615xx import Chroma615xxDriver
from emc.instruments.transport import (
    SimulatedTransport,
    VisaTransport,
    gpib_resource,
    serial_resource,
)
from emc.instruments.ucs500n import UCS500NDriver


def _resource_for(instrument: str, connection: str) -> str:
    if connection == "serial":
        return serial_resource(settings.serial_ports[instrument])
    return gpib_resource(settings.gpib_addresses[instrument])


def build_ucs500n_driver(force_real: bool = False) -> UCS500NDriver:
    if settings.simulation_mode and not force_real:
        transport = SimulatedTransport("UCS500N")
    else:
        transport = VisaTransport(
            "UCS500N", _resource_for("ucs500n", settings.ucs500n_connection)
        )
    return UCS500NDriver(transport)


def build_chroma_driver(force_real: bool = False) -> Chroma615xxDriver:
    if settings.simulation_mode and not force_real:
        transport = SimulatedTransport("Chroma61501")
    else:
        transport = VisaTransport(
            "Chroma61501", _resource_for("chroma", settings.chroma_connection)
        )
    return Chroma615xxDriver(transport)


def build_agilent_counter_driver(force_real: bool = False) -> Agilent53131ACounter:
    return Agilent53131ACounter(
        connection=settings.counter_connection,
        gpib_address=settings.gpib_addresses["agilent_53131a"],
        gpib_board=settings.gpib_boards["agilent_53131a"],
        serial_port=settings.serial_ports["agilent_53131a"],
        simulate=False if force_real else settings.simulation_mode,
    )


def build_driver_for_standard(standard_code: str):
    if standard_code in ("4-4", "4-5"):
        return build_ucs500n_driver()
    if standard_code == "4-11":
        return build_chroma_driver()
    raise ValueError(f"Nenhum driver de automação disponível para a norma {standard_code}")
