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


# Cada instrumento deste modulo corresponde a um dispositivo do cadastro
# unico. Endereco, placa, porta serial e tipo de conexao passaram a ser
# campos da FICHA do dispositivo (aba Dispositivos), como no RadiMation --
# nao mais uma lista de enderecos soltos na tela de Configuracoes.
DISPOSITIVO_DE = {
    "ucs500n": "ucs500n",
    "chroma": "chroma_615xx",
    "agilent_53131a": "agilent_53131a",
}


def _ficha(instrumento: str):
    """Ficha do dispositivo no cadastro unico, ou None.

    Envolvido em try/except de proposito: o pacote emc/ tem que continuar
    funcionando mesmo sem o cadastro (por exemplo, rodando sozinho)."""
    try:
        from core.dispositivos import carregar, caminho
        p = caminho(DISPOSITIVO_DE.get(instrumento, instrumento))
        return carregar(p) if p.exists() else None
    except Exception:
        return None


@dataclass
class RuntimeSettings:
    """Ajustes que valem para o programa todo.

    O que e do APARELHO (endereco, placa, porta, tipo de conexao) nao mora
    mais aqui: vem da ficha do dispositivo. As propriedades abaixo mantem a
    mesma interface de antes -- `settings.gpib_addresses["chroma"]` continua
    valendo -- mas leem do cadastro, caindo no padrao quando o dispositivo
    ainda nao foi cadastrado."""
    simulation_mode: bool = SIMULATION_MODE
    buzzer_enabled: bool = True

    @property
    def gpib_addresses(self) -> dict:
        saida = dict(DEFAULT_GPIB_ADDRESSES)
        for chave in saida:
            d = _ficha(chave)
            if d is not None:
                saida[chave] = d.conexao.endereco
        return saida

    @property
    def gpib_boards(self) -> dict:
        saida = dict(DEFAULT_GPIB_BOARDS)
        for chave in DISPOSITIVO_DE:
            d = _ficha(chave)
            if d is not None:
                saida[chave] = d.conexao.placa
        return saida

    @property
    def serial_ports(self) -> dict:
        saida = dict(DEFAULT_SERIAL_PORTS)
        for chave in saida:
            d = _ficha(chave)
            if d is not None:
                saida[chave] = d.conexao.porta_serial
        return saida

    def _conexao(self, instrumento: str, padrao: str) -> str:
        d = _ficha(instrumento)
        if d is None:
            return padrao
        # a ficha guarda o nome VISA da interface; os drivers do EMC falam
        # em "gpib" ou "serial"
        return "serial" if (d.conexao.interface or "").upper() == "ASRL" else "gpib"

    @property
    def ucs500n_connection(self) -> str:
        return self._conexao("ucs500n", DEFAULT_UCS500N_CONNECTION)

    @property
    def chroma_connection(self) -> str:
        return self._conexao("chroma", DEFAULT_CHROMA_CONNECTION)

    @property
    def counter_connection(self) -> str:
        return self._conexao("agilent_53131a", DEFAULT_COUNTER_CONNECTION)


settings = RuntimeSettings()
