import logging
import random
import time

from emc.config import SIMULATION_MODE
from emc.core.command_overrides import load_overrides
from emc.instruments import agilent_53131a_commands as cmd

logger = logging.getLogger(__name__)


class _SimulatedCounterTransport:
    """Fake instrument pra rodar sem GPIB real conectado."""

    def __init__(self):
        self._base_count = 999_990

    def write(self, command: str) -> None:
        logger.info("[SIM Agilent53131A] -> %s", command)

    def query(self, command: str) -> str:
        self.write(command)
        cmd = command.strip().upper()
        if cmd.startswith("*IDN?"):
            return "Agilent Technologies,53131A,SIM00000,SIM-3.0"
        if cmd.startswith(":FETC"):
            value = self._base_count + random.randint(-5, 5)
            return f"{value:+.5E}"
        return "0"

    def close(self) -> None:
        pass


class Agilent53131ACounter:
    """Driver pro contador de frequência Agilent 53131A, usado no ensaio de
    RTC/Timer (mede a contagem total de pulsos do oscilador do medidor
    durante um tempo de gate fixo — :CONFigure:TOTalize:TIMed). Conecta via
    GPIB ou RS-232 (serial) — os comandos SCPI são os mesmos nos dois casos.

    Sequência de comandos baseada nos scripts validados em campo
    (TIMER_RTC_TESTE.py para GPIB, Timer_RTC.py para RS-232): configura o
    gate, dispara com INIT, aguarda o gate terminar e só então consulta o
    resultado. Confirmado em campo (erro SCPI -213 "Init ignored") que a
    leitura final precisa ser :FETCh? — não :MEASure:...? — porque esse
    último dispara outro INIT por dentro.
    """

    def __init__(
        self,
        connection: str = "gpib",  # "gpib" ou "serial"
        gpib_address: int = 1,
        gpib_board: int = 0,
        serial_port: int = 3,
        serial_baud_rate: int = 9600,
        simulate: bool | None = None,
        timeout_ms: int = 10000,
    ):
        self.connection = connection
        self.gpib_address = gpib_address
        self.gpib_board = gpib_board
        self.serial_port = serial_port
        self.serial_baud_rate = serial_baud_rate
        self.simulate = SIMULATION_MODE if simulate is None else simulate
        self.timeout_ms = timeout_ms
        self._inst = None

    def connect(self) -> None:
        if self.simulate:
            self._inst = _SimulatedCounterTransport()
            logger.info("[SIM Agilent53131A] conectado")
            return

        import pyvisa

        rm = pyvisa.ResourceManager()
        if self.connection == "serial":
            resource = f"ASRL{self.serial_port}::INSTR"
            self._inst = rm.open_resource(resource)
            # mesma configuração de porta do script validado em campo
            # (Timer_RTC.py): 9600 baud, 8 bits, sem paridade, 1 stop bit.
            self._inst.baud_rate = self.serial_baud_rate
            self._inst.data_bits = 8
            self._inst.parity = pyvisa.constants.Parity.none
            self._inst.stop_bits = pyvisa.constants.StopBits.one
        else:
            resource = f"GPIB{self.gpib_board}::{self.gpib_address}::INSTR"
            self._inst = rm.open_resource(resource)
        self._inst.timeout = self.timeout_ms
        logger.info("[Agilent53131A] conectado em %s", resource)

    def disconnect(self) -> None:
        if self._inst is not None:
            try:
                self._inst.close()
            except Exception:
                pass
            self._inst = None

    def _cmd(self, name: str, **kwargs) -> str:
        """Monta a string de comando, usando o valor salvo na aba Comandos se
        o operador já tiver descoberto/confirmado um, senão cai no padrão de
        app/instruments/agilent_53131a_commands.py."""
        overrides = load_overrides("agilent_53131a")
        template = overrides.get(name) or getattr(cmd, name)
        return template.format(**kwargs) if kwargs else template

    def idn(self) -> str:
        return self._inst.query(self._cmd("IDN_QUERY")).strip()

    def recall(self, register: int) -> None:
        """Carrega o estado salvo no registro indicado do instrumento
        (equivalente a apertar Save/Recall > Recall N no painel frontal)."""
        self._inst.write(self._cmd("RECALL", register=register))

    def read_totalize(self, gate_time_s: float) -> float:
        """Configura e mede a contagem total de pulsos durante gate_time_s
        segundos: CONFigure + INIT + aguarda o gate + FETCh? (consulta só o
        resultado, sem disparar outro INIT). Modo 'configuração manual' —
        sobrescreve qualquer configuração carregada por Recall.

        Usa FETCh? em vez de :MEASure:TOTalize:TIMed? porque esse último já
        faz seu próprio INIT por dentro (é um comando "configura+dispara+lê"
        combinado) — encadeado depois de um INIT manual, o instrumento recusa
        o segundo INIT com o erro SCPI -213 "Init ignored"."""
        self._inst.write(self._cmd("CONFIGURE_TOTALIZE_TIMED", gate_time_s=gate_time_s))
        self._inst.write(self._cmd("INIT"))
        time.sleep(gate_time_s + 0.2)
        value = self._inst.query(self._cmd("FETCH"))
        return float(value)

    def read_current_blocking(self, timeout_ms: int = 65000) -> float:
        """Espera o próximo resultado ficar pronto e lê (:FETCh?) usando a
        configuração ATUALMENTE ativa no instrumento (a que veio de um
        Recall, ou a que já estava configurada no painel) — sem mandar INIT
        algum. Bloqueia até timeout_ms esperando a resposta.

        Importante: sempre espera a resposta completa de uma consulta antes
        de mandar a próxima — mandar uma nova consulta com uma resposta
        anterior ainda pendente (ex.: depois de um timeout curto, tentando
        de novo rápido) deixa o barramento fora de sincronia e o instrumento
        recusa com o erro SCPI -420 'Query UNTERMINATED'."""
        if self.simulate:
            return float(self._inst.query(self._cmd("FETCH")))

        original_timeout = self._inst.timeout
        self._inst.timeout = timeout_ms
        try:
            value = self._inst.query(self._cmd("FETCH"))
            return float(value)
        finally:
            self._inst.timeout = original_timeout
