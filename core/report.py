"""
core/report.py

Gera um relatorio PDF simples (1-2 paginas) com: cabecalho do EUT,
grafico medicao x limite, tabela de resultados por detector
(pior margem, frequencia critica, veredito). Usa reportlab, que ja
esta disponivel no ambiente.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, Table,
                                 TableStyle)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from core.evaluation import EvaluationResult, detect_peaks
from core.limits import StandardMethod
from core.trace import Trace
from core.plotting import build_figure

# Rotulos e ordem de coluna identicos aos da tabela "Picos Detectados" dos
# relatorios do laboratorio. A ordem vem da propria consulta do template
# RadiMation embutida no .docx:
#   SELECT Peak Number, Frequency, Average, [Average Limit],
#          [Average Difference], Quasi-Peak, [Quasi-Peak Limit],
#          [Quasi-Peak Difference], Status FROM Emission Table
_DETECTOR_LABELS = {"AV": "Average", "QP": "Quasi-Peak", "PK": "Peak",
                    "CAV": "CISPR Average", "CRMS": "RMS-Average", "RMS": "RMS"}
_DETECTOR_ORDER = {"AV": 0, "QP": 1, "PK": 2, "CAV": 3, "CRMS": 4, "RMS": 5}

# A unidade e escrita por extenso dentro de cada celula (nao no cabecalho),
# igual ao relatorio: "34,2 dBuV", "46 dBuV", "-11,8 dB".
_UNIT_DISPLAY = {"dBuV": "dBµV", "dBuA": "dBµA",
                 "dBuV/m": "dBµV/m", "dBuA/m": "dBµA/m"}


def _detector_label(detector: str) -> str:
    return _DETECTOR_LABELS.get(detector, detector)


def _unit_display(unit: str) -> str:
    return _UNIT_DISPLAY.get(unit, unit)


def _br(x: float | None, decimals: int) -> str:
    """Numero no formato brasileiro (virgula decimal)."""
    if x is None:
        return "-"
    return f"{x:.{decimals}f}".replace(".", ",")


# No relatorio impresso a unidade fica NO CABECALHO, entre parenteses, e a
# celula traz so o numero -- com 1 casa decimal sempre, inclusive o ",0"
# ("46,0" e nao "46"). A frequencia vai em MHz com 3 casas, sem unidade.
def _level(x: float | None) -> str:
    return "-" if x is None else _br(x, 1)


def _difference(x: float | None) -> str:
    return "-" if x is None else _br(x, 1)


def _frequency(f_hz: float) -> str:
    return _br(f_hz / 1e6, 3)


def _fmt_freq_range(f0: float, f1: float) -> str:
    """Faixa no estilo da tabela de incertezas do relatorio: '9 kHz – 150 kHz'."""
    def um(f: float) -> str:
        if f >= 1e6:
            return f"{_br(f / 1e6, 1).rstrip('0').rstrip(',')} MHz"
        if f >= 1e3:
            return f"{_br(f / 1e3, 0)} kHz"
        return f"{_br(f, 0)} Hz"
    return f"{um(f0)} – {um(f1)}"


@dataclass
class ReportInfo:
    eut_name: str = ""
    eut_serial: str = ""
    operator: str = ""
    lab: str = ""
    receiver_model: str = ""
    lisn_or_antenna: str = ""
    extra_notes: str = ""


def generate_pdf_report(out_path: str | Path, trace: Trace, method: StandardMethod,
                         results: list[EvaluationResult], info: ReportInfo,
                         detector_traces: dict[str, Trace] | None = None,
                         incerteza=None, regra_4_1: bool = True,
                         medicao_final=None) -> Path:
    """Gera o PDF do ensaio.

    `detector_traces` (opcional) leva um trace por detector -- ex.:
    {"AV": trace_average, "QP": trace_quasi_peak} -- para que a tabela
    "Picos Detectados" mostre o valor medido de cada detector, como no
    relatorio do laboratorio. Sem ele, todos os detectores usam o mesmo
    trace."""
    out_path = Path(out_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=14)
    normal = styles["Normal"]

    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=15 * mm, bottomMargin=15 * mm)
    story = []
    story.append(Paragraph(f"Relatorio de ensaio EMC - {method.title}", title_style))
    story.append(Paragraph(method.standard_ref, normal))
    story.append(Spacer(1, 6))

    meta_rows = [
        ["EUT", info.eut_name, "N/serie", info.eut_serial],
        ["Operador", info.operator, "Laboratorio", info.lab],
        ["Receiver", info.receiver_model, "LISN/Antena", info.lisn_or_antenna],
        ["Data", datetime.now().strftime("%d/%m/%Y %H:%M"), "Arquivo", trace.source_file or "-"],
    ]
    meta_table = Table(meta_rows, colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    fig = build_figure(trace, method, results, detector_traces=detector_traces)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    story.append(Image(buf, width=170 * mm, height=170 * mm * (5.6 / 9)))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Picos Detectados:", ParagraphStyle("H3", parent=normal, fontSize=10,
                                                                 fontName="Helvetica-Bold")))
    story.append(Spacer(1, 4))

    detectors = sorted({ll.detector for ll in method.limit_lines},
                        key=lambda d: (_DETECTOR_ORDER.get(d, 99), d))
    # A medicao final manda nos valores: e ela que foi feita com o
    # detector de norma, na frequencia exata. O prescan so localizou.
    peaks = detect_peaks(trace, method, detector_traces=detector_traces,
                          medicao_final=medicao_final,
                          regra_4_1=regra_4_1)

    if not peaks:
        story.append(Paragraph("Nenhum pico detectado.",
                                ParagraphStyle("Italic", parent=normal, fontSize=9)))
    else:
        # No relatorio, "Peak Number" e "Status" saem em corpo maior que as
        # colunas de medida.
        head_style = ParagraphStyle("PeakHead", parent=normal, fontSize=8,
                                     fontName="Helvetica-Bold", alignment=1, leading=9.5)
        head_big = ParagraphStyle("PeakHeadBig", parent=head_style, fontSize=10,
                                   leading=12)

        # "Quasi-Peak" tem que quebrar NO HIFEN ("Quasi-" / "Peak"), como no
        # relatorio -- sem isso o reportlab parte no meio da palavra.
        def head(text: str) -> str:
            return text.replace("-", "-<br/>")

        header = [Paragraph("Peak<br/>Number", head_big),
                  Paragraph("Frequency<br/>(MHz)", head_style)]
        for det in detectors:
            label = _detector_label(det)
            unit = _unit_display(next(ll.unit for ll in method.limit_lines
                                       if ll.detector == det))
            header += [Paragraph(head(f"{label} ({unit})"), head_style),
                       Paragraph(head(f"{label} Limit ({unit})"), head_style),
                       Paragraph(head(f"{label} Difference (dB)"), head_style)]
        header.append(Paragraph("Status", head_big))

        rows = [header]
        for i, peak in enumerate(peaks, start=1):
            row = [str(i), _frequency(peak.freq_hz)]
            for det in detectors:
                row += [_level(peak.level_for(det)), _level(peak.limits.get(det)),
                        _difference(peak.diffs.get(det))]
            row.append(peak.status)
            rows.append(row)

        # Larguras: sobra da pagina distribuida entre as colunas de detector.
        avail = 174 * mm
        fixed = 19 * mm + 22 * mm + 19 * mm  # peak + frequency + status
        n_det_cols = len(detectors) * 3
        det_w = (avail - fixed) / n_det_cols if n_det_cols else 0
        col_widths = [19 * mm, 22 * mm] + [det_w] * n_det_cols + [19 * mm]

        peak_table = Table(rows, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c8c8c8")),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#808080")),
            ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#555555")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        # Listras alternadas (linhas impares com fundo azul bem claro),
        # como no relatorio impresso.
        for i in range(1, len(rows)):
            if i % 2 == 1:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i),
                                    colors.HexColor("#eef2f9")))
        # Status: "Pass" em preto (como no relatorio). "Fail" em vermelho --
        # o relatorio de referencia so tem picos aprovados, entao nao da para
        # copiar; vermelho e a convencao usual e ajuda a achar a reprovacao.
        status_col = len(header) - 1
        for i, peak in enumerate(peaks, start=1):
            if peak.status == "Fail":
                style_cmds.append(("TEXTCOLOR", (status_col, i), (status_col, i), colors.red))
                style_cmds.append(("FONTNAME", (status_col, i), (status_col, i), "Helvetica-Bold"))
            elif peak.status != "Pass":
                # "Indet." -- item 4.1: QP acima do limite de media nao reprova,
                # so exige medir com o detector de media.
                style_cmds.append(("TEXTCOLOR", (status_col, i), (status_col, i),
                                    colors.HexColor("#b8860b")))
        peak_table.setStyle(TableStyle(style_cmds))
        story.append(peak_table)
        if any(p.status not in ("Pass", "Fail") for p in peaks):
            story.append(Spacer(1, 3))
            story.append(Paragraph(
                "Indet. — nivel medido em quase-pico acima do limite de media. Conforme o "
                "item 4.1 da CISPR 15, o nivel de quase-pico e um limite superior do de "
                "media: nada se conclui sobre o limite de media sem medir com esse "
                "detector. Nao e reprovacao.",
                ParagraphStyle("Nota41", parent=normal, fontSize=7.5,
                                textColor=colors.HexColor("#8a6d00"))))
    story.append(Spacer(1, 8))

    # ---- Incertezas de medicao + regra de decisao ----
    if incerteza is not None and incerteza.faixas:
        story.append(Paragraph("Incertezas de Medicao (IM)",
                                ParagraphStyle("H3b", parent=normal, fontSize=10,
                                                fontName="Helvetica-Bold")))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            "A incerteza expandida de medicao relatada e declarada como a incerteza padrao "
            "de medicao multiplicada pelo fator de abrangencia k, para um nivel de confianca "
            "de aproximadamente 95%.",
            ParagraphStyle("Small", parent=normal, fontSize=8)))
        story.append(Spacer(1, 4))

        unc_head = ParagraphStyle("UncHead", parent=normal, fontSize=8,
                                   fontName="Helvetica-Bold", alignment=1, leading=9.5)
        unc_rows = [[Paragraph(t, unc_head) for t in
                     ("Item da norma", "Mensurando", "Faixa ou ponto de medicao",
                      "Incerteza de medicao", "Fator de abrangencia (k)")]]
        for f in incerteza.faixas:
            unc_rows.append([
                f.item_norma or "-",
                f.mensurando or "-",
                f"{_fmt_freq_range(f.freq_min_hz, f.freq_max_hz)}",
                f"{_br(f.u_lab_db, 1)} dB",
                _br(f.fator_k, 2),
            ])
        unc_table = Table(unc_rows, colWidths=[24 * mm, 42 * mm, 44 * mm, 30 * mm, 34 * mm])
        unc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(unc_table)
        story.append(Spacer(1, 5))
        story.append(Paragraph(
            f"<b>Regra de decisao aplicada:</b> {incerteza.descricao_regra()}",
            ParagraphStyle("Rule", parent=normal, fontSize=8)))
        story.append(Spacer(1, 8))

    if any(not ll.is_fully_verified() for ll in method.limit_lines):
        warn = ("AVISO: um ou mais segmentos da linha de limite usada neste relatorio NAO "
                "estao marcados como verificados contra o texto oficial da norma "
                "(ver core/standards/*.json). Este relatorio nao deve ser usado como "
                "laudo final de conformidade ate a confirmacao dos valores de limite.")
        story.append(Paragraph(warn, ParagraphStyle("Warn", parent=normal, textColor=colors.red, fontSize=8)))
        story.append(Spacer(1, 4))

    if info.extra_notes:
        story.append(Paragraph(f"Observacoes: {info.extra_notes}", normal))

    doc.build(story)
    return out_path
