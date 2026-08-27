"""
scripts/gerar_icone.py

Gera assets/halo.ico a partir do logotipo desenhado em gui/theme.py.

O logotipo do HALO nao e um arquivo de imagem -- e codigo (QPainter). Para
o Windows usar o icone num atalho da area de trabalho ele precisa de um
.ico de verdade, com varios tamanhos dentro: 16 px aparece na barra de
titulo, 32 px na barra de tarefas, 48 px na area de trabalho, 256 px na
visualizacao grande do Explorer.

O .ico e montado a mao: o formato e um cabecalho de 6 bytes, uma entrada
de 16 bytes por tamanho e, na sequencia, os PNGs. O Windows aceita PNG
dentro de .ico desde o Vista, o que evita ter que escrever BMP com mascara.

Rode com:  python scripts/gerar_icone.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice   # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

TAMANHOS = (16, 24, 32, 48, 64, 128, 256)
DESTINO = RAIZ / "assets" / "halo.ico"


def _png_bytes(size: int) -> bytes:
    from gui import theme
    px = theme.logo_pixmap(size)
    # o QByteArray precisa sobreviver ao QBuffer: passado como temporario,
    # o Python o coleta e o Qt escreve em memoria liberada (segfault)
    dados = QByteArray()
    buf = QBuffer(dados)
    buf.open(QIODevice.WriteOnly)
    px.save(buf, "PNG")
    buf.close()
    return bytes(dados)


def gerar(destino: Path = DESTINO) -> Path:
    imagens = [(s, _png_bytes(s)) for s in TAMANHOS]

    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))   # reservado, tipo=icone, qtd
    deslocamento = len(cabecalho) + 16 * len(imagens)
    entradas, dados = b"", b""
    for lado, png in imagens:
        entradas += struct.pack(
            "<BBBBHHII",
            0 if lado >= 256 else lado,   # largura (0 = 256)
            0 if lado >= 256 else lado,   # altura
            0,                            # cores da paleta (0 = truecolor)
            0,                            # reservado
            1,                            # planos de cor
            32,                           # bits por pixel
            len(png),
            deslocamento,
        )
        dados += png
        deslocamento += len(png)

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cabecalho + entradas + dados)
    return destino


def main():
    # QPixmap exige um QApplication vivo; a referencia fica ate o fim do
    # processo de proposito -- destrui-la antes derruba o Qt.
    global _app
    _app = QApplication.instance() or QApplication(sys.argv)
    caminho = gerar()
    print(f"icone gerado: {caminho} ({caminho.stat().st_size} bytes, "
          f"{len(TAMANHOS)} tamanhos: {', '.join(map(str, TAMANHOS))})")


if __name__ == "__main__":
    main()
