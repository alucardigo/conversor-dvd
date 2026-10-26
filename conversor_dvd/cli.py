"""Linha de comando. Sem argumentos, abre a janela."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .conversao import FORMATOS, PERFIS, Cancelado, ErroConversao, Opcoes, converter, formatar_duracao, pasta_padrao
from .ffmpeg import FFmpeg, FFmpegAusente
from .fontes import ErroFonte, Titulo, analisar, ler_lista_numeros, selecionar

EXEMPLOS = """exemplos:
  conversor-dvd E:\\                          todos os títulos do DVD da unidade E: para MP4
  conversor-dvd E:\\ -f ambos -q alta          MP4 e AVI, qualidade alta
  conversor-dvd D:\\Copias\\Filme --listar  só mostra o que há no disco
  conversor-dvd filme.iso -t 2,4 -f avi        títulos 2 e 4 da ISO, em AVI
  conversor-dvd D:\\DVDs -o D:\\Videos          todos os discos de uma pasta (lote)
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="conversor-dvd",
        description="Converte DVDs antigos (VIDEO_TS, ISO, DVD-VR, VCD, VOB, MPEG de filmadora) para MP4 ou AVI.",
        epilog=EXEMPLOS, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("entrada", nargs="?", help="unidade (E:\\), pasta, VIDEO_TS, ISO ou arquivo de vídeo")
    p.add_argument("-o", "--saida", type=Path, default=pasta_padrao(), help="pasta de destino (padrão: %(default)s)")
    p.add_argument("-f", "--formato", choices=[*FORMATOS, "ambos"], default="mp4", help="padrão: mp4")
    p.add_argument("-q", "--qualidade", choices=list(PERFIS), default="media", help="padrão: media")
    p.add_argument("-t", "--titulos", type=ler_lista_numeros, help="números da listagem, ex.: 1,3-5")
    p.add_argument("--maior", action="store_true", help="só o título mais longo (o filme, num DVD comercial)")
    p.add_argument("--minimo", type=float, default=10.0, help="ignora títulos mais curtos que N segundos (padrão: 10)")
    p.add_argument("--sem-desentrelacar", action="store_true", help="não desentrelaça (vídeo já progressivo)")
    p.add_argument("--listar", action="store_true", help="só lista os títulos, sem converter")
    return p


def _listar(titulos: list[Titulo]) -> None:
    print(f"\n  {'#':>2}  {'Duração':>8}  {'Tipo':<10} {'Título':<34} Detalhes")
    for n, t in enumerate(titulos, 1):
        print(f"  {n:>2}  {formatar_duracao(t.duracao):>8}  {t.tipo:<10} {t.rotulo:<34} {t.info}")
    print()


class _Barra:
    def __init__(self) -> None:
        self.ultimo = -1

    def __call__(self, fracao: float) -> None:
        pct = int(fracao * 100)
        if pct != self.ultimo:
            self.ultimo = pct
            print(f"\r     {pct:3d}%", end="", flush=True)


def _converter_todos(ff: FFmpeg, tarefas: list[tuple[Titulo, str]], destino: Path, opcoes: Opcoes) -> int:
    falhas = 0
    for i, (titulo, formato) in enumerate(tarefas, 1):
        print(f"[{i}/{len(tarefas)}] {titulo.rotulo} -> {formato.upper()} ({formatar_duracao(titulo.duracao)})")
        try:
            saida = converter(ff, titulo, formato, destino, opcoes, ao_progredir=_Barra())
        except (ErroConversao, OSError) as e:  # OSError: disco cheio, ffmpeg bloqueado; o lote segue
            falhas += 1
            print(f"\n     ERRO: {e}", file=sys.stderr)
        else:
            print(f"\n     ok: {saida}")
    return falhas


def _saida_em_utf8() -> None:
    # Redirecionado para arquivo/pipe, o Windows usaria cp1252 e estragaria "Título".
    for fluxo in (sys.stdout, sys.stderr):
        if fluxo is not None and hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _saida_em_utf8()
    args = _parser().parse_args(argv)
    if args.entrada is None:
        from .gui import main as abrir_janela

        abrir_janela()
        return 0
    try:
        ff = FFmpeg.localizar()
        titulos = analisar(args.entrada, ff, relatar=lambda msg: print(msg, file=sys.stderr))
        _listar(titulos)
        if args.listar:
            return 0
        escolhidos = selecionar(titulos, args.minimo, args.titulos, args.maior)
    except (FFmpegAusente, ErroFonte, ValueError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2
    formatos = FORMATOS if args.formato == "ambos" else (args.formato,)
    tarefas = [(t, f) for t in escolhidos for f in formatos]
    opcoes = Opcoes(args.qualidade, not args.sem_desentrelacar)
    try:
        falhas = _converter_todos(ff, tarefas, args.saida, opcoes)
    except (KeyboardInterrupt, Cancelado):
        print("\nCancelado.", file=sys.stderr)
        return 130
    print(f"\n{len(tarefas) - falhas} de {len(tarefas)} arquivo(s) em {args.saida}")
    return 1 if falhas else 0
