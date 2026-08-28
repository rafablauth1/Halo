"""
core/dispositivos.py

Cadastro unico de dispositivos, no modelo "Device Driver" do RadiMation.

Ate aqui o programa tinha DOIS cadastros que nao se falavam:

  * `instruments/receiver_models.py` -- 31 receivers R&S, com comandos SCPI,
    editor na tela e heranca de comando, mas de UM tipo so;
  * `core/equipamentos.py` -- cabos, LISNs, antenas e atenuadores, com
    certificado de calibracao interpolado, mas sem nenhum comando.

E os instrumentos de imunidade (UCS 500N, Chroma, Agilent) nao estavam em
cadastro nenhum: os comandos eram constantes dentro do modulo do driver.

Aqui os tres viram a mesma coisa. Um dispositivo tem TIPO (os 33 tipos do
RadiMation mais os que o laboratorio usa e a lista nao nomeia), ficha do
modelo, conexao, comandos e certificados. Qualquer tipo pode ter comando e
qualquer tipo pode ter certificado -- um cabo normalmente so tem
certificado, um gerador de surto normalmente so tem comando, mas nada
impede os dois, e num laboratorio de metrologia legal os dois costumam
ser exigidos.

Compatibilidade: este modulo NAO apaga os cadastros antigos. Ele sabe
importar de ambos (`importar_receivers`, `importar_equipamentos`), e os
programas antigos continuam lendo os seus arquivos enquanto a migracao
nao termina.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

from core.equipamentos import Certificado, PontoCertificado

DISPOSITIVOS_DIR = Path(__file__).parent.parent / "dados" / "dispositivos"

_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


# ---------------------------------------------------------------------------
# Tipos de dispositivo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TipoDispositivo:
    id: str
    nome: str
    grupo: str            # como o tipo aparece agrupado na tela
    comandos: bool        # o tipo costuma ser controlado remotamente
    correcao: bool        # o tipo costuma ter fator/perda a corrigir
    nota: str = ""


def _t(id, nome, grupo, comandos, correcao, nota=""):
    return TipoDispositivo(id, nome, grupo, comandos, correcao, nota)


# Os 33 tipos do RadiMation (RadiWiki > Device Types), na mesma ordem, mais
# os que o laboratorio usa e a lista nao nomeia -- marcados na nota.
TIPOS: dict[str, TipoDispositivo] = {t.id: t for t in [
    # --- medicao ---
    _t("ad_converter",     "Conversor A/D",            "Medição", True,  False),
    _t("spectrum_analyser", "Analisador de espectro",  "Medição", True,  False),
    _t("receiver",         "Receiver de EMI",          "Medição", True,  False,
       "Fora da lista do RadiMation, que trata o receiver como analisador."),
    _t("network_analyser", "Analisador de redes",      "Medição", True,  False),
    _t("oscilloscope",     "Osciloscópio",             "Medição", True,  False),
    _t("multimeter",       "Multímetro",               "Medição", True,  False),
    _t("frequency_counter", "Contador de frequência",  "Medição", True,  False,
       "Fora da lista do RadiMation. Agilent 53131A."),
    _t("forward_power_meter",  "Medidor de potência direta",   "Medição", True, False),
    _t("reflected_power_meter", "Medidor de potência refletida", "Medição", True, False),
    _t("output_power_meter",   "Medidor de potência de saída",  "Medição", True, False),
    _t("sensor_power_meter",   "Sensor de potência",            "Medição", True, True),

    # --- geracao e amplificacao ---
    _t("signal_generator", "Gerador de sinal",         "Geração", True,  False),
    _t("modulation_source", "Fonte de modulação",      "Geração", True,  False),
    _t("amplifier",        "Amplificador",             "Geração", True,  True),
    _t("pre_amplifier",    "Pré-amplificador",         "Geração", True,  True),
    _t("ac_source",        "Fonte CA programável",     "Geração", True,  False,
       "Fora da lista do RadiMation. Chroma 61501/61504, usada na IEC 61000-4-11."),

    # --- geradores de ensaio de imunidade ---
    _t("eft_burst_generator", "Gerador de burst (EFT)", "Imunidade", True, False,
       "IEC 61000-4-4."),
    _t("surge_generator",  "Gerador de surto",         "Imunidade", True,  False,
       "IEC 61000-4-5."),
    _t("esd_generator",    "Gerador de ESD",           "Imunidade", True,  False,
       "IEC 61000-4-2."),
    _t("injection_device", "Dispositivo de injeção",   "Imunidade", True,  True,
       "IEC 61000-4-6."),
    _t("coupler",          "Rede de acoplamento",      "Imunidade", True,  True),
    _t("output_coupler",   "Acoplador de saída",       "Imunidade", False, True),

    # --- transdutores e acessorios de RF ---
    _t("antenna",          "Antena",                   "Transdutores", False, True),
    _t("calibration_antenna", "Antena de calibração",  "Transdutores", False, True),
    _t("absorbing_clamp",  "Pinça absorvedora",        "Transdutores", False, True),
    _t("current_sensor",   "Sensor de corrente",       "Transdutores", False, True),
    _t("field_sensor",     "Sensor de campo",          "Transdutores", True,  True),
    _t("lisn",             "LISN / rede de estabilização", "Transdutores", True, True),
    _t("cable",            "Cabo",                     "Transdutores", False, True),
    _t("attenuator",       "Atenuador",                "Transdutores", False, True,
       "Fora da lista do RadiMation, que o trata como resistor."),
    _t("resistor",         "Resistor",                 "Transdutores", False, True),
    _t("jig",              "Dispositivo de fixação (jig)", "Transdutores", False, True),
    _t("switch_matrix",    "Matriz de comutação",      "Transdutores", True,  False),

    # --- posicionamento ---
    _t("turn_table",       "Mesa giratória",           "Posicionamento", True, False),
    _t("antenna_tower",    "Mastro de antena",         "Posicionamento", True, False),
    _t("positioner",       "Posicionador",             "Posicionamento", True, False),

    # --- controle do EUT ---
    _t("eut_controller",   "Controlador do EUT",       "EUT", True, False),

    # --- padroes de metrologia legal ------------------------------------
    # Um laboratorio de metrologia legal ensaia INSTRUMENTOS DE MEDICAO
    # regulamentados, e os padroes usados para conferi-los tambem precisam
    # de certificado rastreado. Nao existem na lista do RadiMation porque
    # ela e de EMC pura.
    _t("padrao_volume",    "Padrão de volume",         "Metrologia legal", False, True,
       "Medidor de água, de gás, bomba de combustível."),
    _t("padrao_massa",     "Padrão de massa",          "Metrologia legal", False, True),
    _t("padrao_tempo",     "Padrão de tempo / frequência", "Metrologia legal", True, True,
       "Taxímetro, medidor de velocidade."),
    _t("padrao_energia",   "Padrão de energia elétrica", "Metrologia legal", True, True,
       "Medidor de energia."),
    _t("padrao_gas",       "Padrão de concentração de gás", "Metrologia legal", False, True,
       "Etilômetro, analisador de gases."),
    _t("padrao_temperatura", "Padrão de temperatura",  "Metrologia legal", True, True),
    _t("padrao_pressao",   "Padrão de pressão",        "Metrologia legal", True, True),
]}

GRUPOS = ["Medição", "Geração", "Imunidade", "Transdutores",
          "Posicionamento", "EUT", "Metrologia legal"]


def tipos_do_grupo(grupo: str) -> list[TipoDispositivo]:
    return [t for t in TIPOS.values() if t.grupo == grupo]


# ---------------------------------------------------------------------------
# Conexao
# ---------------------------------------------------------------------------

INTERFACES = ("nenhuma", "GPIB", "TCPIP", "USB", "ASRL")


@dataclass
class Conexao:
    """Como se fala com o dispositivo. `nenhuma` para o que é passivo --
    um cabo ou um atenuador não tem endereço."""
    interface: str = "nenhuma"
    placa: int = 0
    endereco: int = 20
    host: str = "192.168.0.100"
    porta_serial: int = 3
    timeout_ms: int = 20000

    def recurso_visa(self) -> str:
        """String VISA montada a partir dos campos. Vazia se passivo."""
        i = (self.interface or "nenhuma").upper()
        if i == "GPIB":
            return f"GPIB{self.placa}::{self.endereco}::INSTR"
        if i == "TCPIP":
            return f"TCPIP0::{self.host}::INSTR"
        if i == "USB":
            return f"USB0::{self.endereco}::INSTR"
        if i == "ASRL":
            return f"ASRL{self.porta_serial}::INSTR"
        return ""

    def ativa(self) -> bool:
        return (self.interface or "nenhuma").lower() != "nenhuma"


# ---------------------------------------------------------------------------
# Dispositivo
# ---------------------------------------------------------------------------

@dataclass
class Dispositivo:
    id: str
    tipo: str = "cable"
    fabricante: str = ""
    modelo: str = ""
    numero_serie: str = ""
    patrimonio: str = ""
    descricao: str = ""

    conexao: Conexao = field(default_factory=Conexao)
    comandos: dict[str, str] = field(default_factory=dict)

    # correcao: como o valor do certificado entra na conta
    aplicar: str = "somar"          # somar | subtrair
    certificados: list[Certificado] = field(default_factory=list)

    # ficha tecnica livre, o que cada tipo precisar (faixa, detectores...)
    atributos: dict = field(default_factory=dict)

    verificado: bool = False        # comandos conferidos contra o aparelho
    ativo: bool = True
    notas: str = ""

    # ---- consultas ----
    def tipo_info(self) -> TipoDispositivo:
        return TIPOS.get(self.tipo, TIPOS["cable"])

    def rotulo(self) -> str:
        partes = [p for p in (self.fabricante, self.modelo) if p]
        base = " ".join(partes) or self.id
        if self.numero_serie:
            base += f" (s/n {self.numero_serie})"
        return base

    def certificado(self, quando: Optional[date] = None) -> Optional[Certificado]:
        """O certificado válido na data, ou o mais recente."""
        if not self.certificados:
            return None
        quando = quando or date.today()
        validos = [c for c in self.certificados if not c.vencido_em(quando)]
        alvo = validos or self.certificados
        return max(alvo, key=lambda c: c.data_calibracao or "")

    def precisa_certificado(self) -> bool:
        """Num laboratório de metrologia legal, todo dispositivo que entra
        na cadeia de medição precisa de rastreabilidade. O tipo diz se ele
        entra na conta; a exigência de certificado vale para todos."""
        return True

    def situacao(self) -> str:
        """'ok' | 'sem_certificado' | 'vencido' | 'vence_em_breve'."""
        cert = self.certificado()
        if cert is None or not cert.pontos:
            return "sem_certificado"
        dias = cert.dias_para_vencer()
        if dias is None:
            return "sem_certificado"
        if dias < 0:
            return "vencido"
        if dias < 60:
            return "vence_em_breve"
        return "ok"

    def comando(self, chave: str) -> Optional[str]:
        """Comando do dispositivo, ou None. Mesma regra do catálogo de
        receivers: chave ausente herda o padrão SCPI; chave vazia significa
        que este modelo não tem esse comando."""
        from instruments.receiver_models import BASE_COMMANDS
        if chave in self.comandos:
            c = self.comandos[chave]
            return c or None
        c = BASE_COMMANDS.get(chave, "")
        return c or None


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _id_valido(texto: str) -> str:
    limpo = "".join(ch if ch in _SAFE else "_" for ch in (texto or "").strip())
    return limpo or "dispositivo"


def caminho(disp_id: str) -> Path:
    return DISPOSITIVOS_DIR / f"{_id_valido(disp_id)}.json"


def listar() -> list[Path]:
    DISPOSITIVOS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DISPOSITIVOS_DIR.glob("*.json"))


def carregar(caminho_json: str | Path) -> Dispositivo:
    dados = json.loads(Path(caminho_json).read_text(encoding="utf-8"))
    conexao = Conexao(**dados.pop("conexao", {}) or {})
    certs = []
    for c in dados.pop("certificados", []) or []:
        pontos = [PontoCertificado(**p) for p in c.pop("pontos", []) or []]
        certs.append(Certificado(pontos=pontos, **c))
    return Dispositivo(conexao=conexao, certificados=certs, **dados)


def salvar(d: Dispositivo) -> Path:
    DISPOSITIVOS_DIR.mkdir(parents=True, exist_ok=True)
    p = caminho(d.id)
    p.write_text(json.dumps(asdict(d), indent=2, ensure_ascii=False),
                  encoding="utf-8")
    return p


def excluir(disp_id: str) -> None:
    caminho(disp_id).unlink(missing_ok=True)


def todos() -> list[Dispositivo]:
    saida = []
    for p in listar():
        try:
            saida.append(carregar(p))
        except Exception:
            continue
    return saida


def por_tipo(tipo: str) -> list[Dispositivo]:
    return [d for d in todos() if d.tipo == tipo]


# ---------------------------------------------------------------------------
# Migracao dos cadastros antigos
# ---------------------------------------------------------------------------

def importar_receivers(sobrescrever: bool = False) -> int:
    """Traz os 31 modelos R&S do catálogo de receivers."""
    from instruments.receiver_models import list_available_receivers, load_receiver
    n = 0
    for p in list_available_receivers():
        try:
            m = load_receiver(p)
        except Exception:
            continue
        if caminho(m.id).exists() and not sobrescrever:
            continue
        d = Dispositivo(
            id=m.id, tipo="receiver",
            fabricante=m.manufacturer, modelo=m.model,
            descricao=m.description,
            conexao=Conexao(interface="GPIB", endereco=m.default_gpib_address),
            comandos=dict(m.commands),
            verificado=bool(m.verified),
            notas=m.notes,
            atributos={
                "faixa_hz": [m.freq_min_hz, m.freq_max_hz],
                "detectores": list(m.detectors),
                "rbw_cispr_hz": list(m.rbw_cispr_hz),
                "familia": m.family,
                "pre_amp": m.has_preamp,
                "pre_seletor": m.has_preselector,
                "modo_receiver": m.has_receiver_mode,
                "tabela_scan": m.has_scan_table,
                "controle_lisn": m.has_lisn_control,
            },
        )
        salvar(d)
        n += 1
    return n


_TIPO_ANTIGO = {"cabo": "cable", "lisn": "lisn", "antena": "antenna",
                "atenuador": "attenuator", "pre-amplificador": "pre_amplifier",
                "preamplificador": "pre_amplifier"}


def importar_equipamentos(sobrescrever: bool = False) -> int:
    """Traz cabos, LISNs, antenas e atenuadores, com os certificados."""
    from core.equipamentos import listar_equipamentos, carregar_equipamento
    n = 0
    for p in listar_equipamentos():
        try:
            eq = carregar_equipamento(p)
        except Exception:
            continue
        if caminho(eq.id).exists() and not sobrescrever:
            continue
        d = Dispositivo(
            id=eq.id,
            tipo=_TIPO_ANTIGO.get((eq.tipo or "").lower(), "cable"),
            fabricante=eq.fabricante, modelo=eq.modelo,
            numero_serie=eq.numero_serie, patrimonio=eq.patrimonio,
            descricao=eq.descricao,
            aplicar=eq.aplicar,
            certificados=list(eq.certificados),
            ativo=eq.ativo,
        )
        salvar(d)
        n += 1
    return n


def importar_instrumentos_emc(sobrescrever: bool = False) -> int:
    """Traz UCS 500N, Chroma e Agilent, que só existiam como constantes.

    Estes três são os ÚNICOS com comandos conferidos contra hardware de
    verdade, por isso entram com `verificado=True` -- e as armadilhas
    descobertas em campo viram nota da ficha, em vez de comentário perdido
    no topo de um arquivo .py."""
    fichas = [
        dict(id="ucs500n", tipo="eft_burst_generator",
             fabricante="EM TEST", modelo="UCS 500N",
             descricao="Sistema de imunidade: burst (4-4) e surto (4-5)",
             conexao=Conexao(interface="GPIB", endereco=6),
             verificado=False,
             notas="Os comandos são TENTATIVA: o dicionário oficial do "
                   "fabricante não é público. O aparelho entra em REMOTE "
                   "(prova que o GPIB funciona), mas os comandos podem não "
                   "fazer efeito. Descubra no Terminal e corrija aqui."),
        dict(id="chroma_615xx", tipo="ac_source",
             fabricante="Chroma", modelo="61501/61504",
             descricao="Fonte CA programável — quedas e interrupções (4-11)",
             conexao=Conexao(interface="GPIB", endereco=30),
             verificado=True,
             notas="Validado em campo. ATENÇÃO: 'OUTP:MODE {LIST|PULSE}' "
                   "seguido de 'TRIG ON' não faz o aparelho sair da tensão "
                   "nominal — em dois ensaios reais separados. Só escrever "
                   "VOLT direto e esperar em software muda a saída."),
        dict(id="agilent_53131a", tipo="frequency_counter",
             fabricante="Agilent", modelo="53131A",
             descricao="Contador de frequência",
             conexao=Conexao(interface="GPIB", placa=0, endereco=1),
             verificado=True,
             notas="Validado em campo. Use FETCH e não MEASure? para ler o "
                   "resultado (MEASure? dispara outro INIT e causa o erro "
                   "-213 'Init ignored'). Nunca envie consulta nova sem ter "
                   "lido por completo a resposta da anterior (erro -420)."),
    ]
    n = 0
    for f in fichas:
        if caminho(f["id"]).exists() and not sobrescrever:
            continue
        # comandos vindos dos modulos originais
        f["comandos"] = _comandos_emc(f["id"])
        salvar(Dispositivo(**f))
        n += 1
    return n


def _comandos_emc(disp_id: str) -> dict[str, str]:
    """Le as constantes maiusculas do modulo de comandos do instrumento."""
    modulos = {"ucs500n": "emc.instruments.ucs500n_commands",
               "chroma_615xx": "emc.instruments.chroma_commands",
               "agilent_53131a": "emc.instruments.agilent_53131a_commands"}
    nome = modulos.get(disp_id)
    if not nome:
        return {}
    try:
        import importlib
        mod = importlib.import_module(nome)
    except Exception:
        return {}
    return {k: v for k, v in vars(mod).items()
            if k.isupper() and isinstance(v, str) and not k.startswith("_")}


def migrar_tudo(sobrescrever: bool = False) -> dict[str, int]:
    """Traz os três cadastros antigos para o cadastro único."""
    return {
        "receivers": importar_receivers(sobrescrever),
        "equipamentos": importar_equipamentos(sobrescrever),
        "instrumentos_emc": importar_instrumentos_emc(sobrescrever),
    }
