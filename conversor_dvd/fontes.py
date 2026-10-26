"""Descobre o que há para converter num disco, pasta ou arquivo.

Formatos reconhecidos:
- DVD-Video: pasta VIDEO_TS (ou a própria unidade) e imagem ISO; os títulos saem
  na ordem do IFO pelo demuxer `dvdvideo` do ffmpeg. Se o IFO não abrir, os VOBs
  são concatenados por titleset.
- DVD-VR (gravador de mesa, filmadora): VR_MOVIE.VRO.
- VCD/SVCD: MPEGAV/*.DAT, MPEG2/*.MPG.
- VOBs copiados sem IFO, MPEG solto, .MOD/.TOD de filmadora, AVCHD (.MTS).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .ffmpeg import FFmpeg

EXT_IMAGEM = {".iso", ".img"}
TIPOS_POR_EXTENSAO = {
    ".vob": "VOB", ".vro": "DVD-VR", ".dat": "VCD",
    ".mpg": "MPEG", ".mpeg": "MPEG", ".m2v": "MPEG", ".m2p": "MPEG", ".ts": "MPEG-TS",
    ".mod": "Filmadora", ".tod": "Filmadora", ".mts": "AVCHD", ".m2ts": "AVCHD", ".evo": "HD DVD",
}
# Pastas que fazem parte da estrutura do disco; o nome do disco é o da pasta acima delas.
PASTAS_ESTRUTURAIS = {"VIDEO_TS", "DVD_RTAV", "VIDEO_RM", "MPEGAV", "MPEG2", "SEGMENT", "STREAM", "BDMV", "AVCHD", "PRIVATE"}
RE_VOB_TITULO = re.compile(r"^VTS_(\d{2})_([1-9])\.VOB$", re.IGNORECASE)
RE_VOB_MENU = re.compile(r"^(VIDEO_TS|VTS_\d{2}_0)\.VOB$", re.IGNORECASE)
RE_UNIDADE = re.compile(r"[A-Za-z]:[\\/]?")
PROIBIDOS_EM_NOME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Disco velho tem setor ilegível e fluxo que começa no meio: tolerar em vez de abortar.
ENTRADA_TOLERANTE = ["-fflags", "+genpts+discardcorrupt", "-analyzeduration", "100M", "-probesize", "100M"]
MAX_TITULOS_DVD = 99

Relatar = Callable[[str], None]


class ErroFonte(Exception):
    pass


@dataclass
class Titulo:
    disco: str
    nome: str
    entrada: list[str]
    duracao: float = 0.0
    tipo: str = ""
    info: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.disco} - {self.nome}"


@dataclass(frozen=True)
class Item:
    """Algo a sondar: um DVD-Video (pasta ou ISO) ou um grupo de arquivos que vira um vídeo."""
    tipo: str  # "dvd" | "iso" | "arquivos"
    disco: str
    nome: str
    caminhos: tuple[Path, ...]


# --- planejamento (só sistema de arquivos) -------------------------------------------

def nome_seguro(texto: str) -> str:
    limpo = " ".join(PROIBIDOS_EM_NOME.sub(" ", texto).split()).rstrip(". ")
    return limpo or "DVD"


def _rotulo_do_volume(raiz: Path) -> str:
    if os.name != "nt":
        return ""
    import ctypes

    buffer = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(str(raiz), buffer, 261, None, None, None, None, 0)
    return buffer.value if ok else ""


def nome_disco(pasta: Path) -> str:
    while pasta.name.upper() in PASTAS_ESTRUTURAIS and pasta.parent != pasta:
        pasta = pasta.parent
    if pasta.parent == pasta:  # raiz de unidade, ex.: E:\
        return _rotulo_do_volume(pasta) or f"DVD {pasta.drive.rstrip(':')}"
    return pasta.name


def eh_pasta_dvd(pasta: Path, arquivos: Iterable[str]) -> bool:
    nomes = {a.upper() for a in arquivos}
    if "VIDEO_TS.IFO" in nomes:
        return True
    return pasta.name.upper() == "VIDEO_TS" and any(n.endswith(".VOB") for n in nomes)


def _chave_do_grupo(p: Path) -> tuple[str, str] | None:
    """(chave, nome exibido) do vídeo a que o arquivo pertence; None se não for vídeo."""
    if RE_VOB_MENU.match(p.name):
        return None
    vob = RE_VOB_TITULO.match(p.name)
    if vob:
        return f"VTS_{vob.group(1)}", f"VTS {vob.group(1)}"
    if p.suffix.lower() in TIPOS_POR_EXTENSAO:
        return p.name.upper(), p.stem
    return None


def agrupar_arquivos(arquivos: Iterable[Path]) -> list[tuple[str, list[Path]]]:
    """Partes VTS_nn_1..9.VOB viram um vídeo só; os demais arquivos de vídeo, um cada."""
    grupos: dict[str, tuple[str, list[Path]]] = {}
    for p in sorted(arquivos, key=lambda c: c.name.upper()):
        chave = _chave_do_grupo(p)
        if chave:
            grupos.setdefault(chave[0], (chave[1], []))[1].append(p)
    return sorted(grupos.values(), key=lambda g: g[0].upper())


def _planejar_arquivo(p: Path) -> list[Item]:
    sufixo = p.suffix.lower()
    if sufixo == ".ifo":
        return _planejar_pasta(p.parent)
    if sufixo in EXT_IMAGEM:
        return [Item("iso", p.stem, "", (p,))]
    vob = RE_VOB_TITULO.match(p.name)
    if vob:  # escolheu VTS_02_1.VOB: levar junto VTS_02_2, VTS_02_3...
        nome = f"VTS {vob.group(1)}"
        partes = dict(agrupar_arquivos(p.parent.iterdir()))[nome]
        return [Item("arquivos", nome_disco(p.parent), nome, tuple(partes))]
    if sufixo in TIPOS_POR_EXTENSAO:
        return [Item("arquivos", nome_disco(p.parent), p.stem, (p,))]
    raise ErroFonte(f"Formato não reconhecido: {p.name}")


def _video_ts_do_disco(atual: Path, subpastas: list[str], arquivos: list[str]) -> Path | None:
    """A pasta VIDEO_TS se `atual` for ela ou a raiz de um disco que a contém."""
    if eh_pasta_dvd(atual, arquivos):
        return atual
    for nome in subpastas:
        if nome.upper() == "VIDEO_TS" and eh_pasta_dvd(atual / nome, os.listdir(atual / nome)):
            return atual / nome
    return None


def _planejar_pasta(raiz: Path) -> list[Item]:
    itens: list[Item] = []
    for pasta, subpastas, arquivos in os.walk(raiz):
        atual = Path(pasta)
        subpastas.sort(key=str.upper)
        video_ts = _video_ts_do_disco(atual, subpastas, arquivos)
        if video_ts:
            # O resto do disco (AUDIO_TS, JACKET_P, dados do programa de autoria) não é vídeo.
            subpastas.clear()
            itens.append(Item("dvd", nome_disco(video_ts), "", (video_ts,)))
            continue
        caminhos = [atual / a for a in sorted(arquivos, key=str.upper)]
        itens += [Item("iso", c.stem, "", (c,)) for c in caminhos if c.suffix.lower() in EXT_IMAGEM]
        disco = nome_disco(atual)
        itens += [Item("arquivos", disco, nome, tuple(g)) for nome, g in agrupar_arquivos(caminhos)]
    return itens


def normalizar_entrada(caminho: str | Path) -> Path:
    """Aceita E:, E:/ e o E:" que o cmd entrega quando se digita a unidade entre aspas com barra."""
    texto = str(caminho).strip().strip('"').strip()
    if RE_UNIDADE.fullmatch(texto):
        return Path(texto[0].upper() + ":\\")
    return Path(texto)


def planejar(caminho: str | Path) -> list[Item]:
    p = normalizar_entrada(caminho)
    if not p.exists():
        raise ErroFonte(f"Não encontrei {p}. Confira se o disco está na unidade ou se o caminho está certo.")
    return _planejar_arquivo(p) if p.is_file() else _planejar_pasta(p)


# --- sondagem (ffprobe) ---------------------------------------------------------------

def _streams(info: dict, tipo: str) -> list[dict]:
    return [s for s in info.get("streams", []) if s.get("codec_type") == tipo]


def _duracao(info: dict | None) -> float:
    try:
        return float((info or {}).get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        return 0.0


def _resumo(info: dict) -> str:
    partes = []
    for v in _streams(info, "video")[:1]:
        proporcao = v.get("display_aspect_ratio", "0:1")
        partes.append(f"{v.get('width')}x{v.get('height')}" + (f" {proporcao}" if proporcao != "0:1" else ""))
    n = len(_streams(info, "audio"))
    partes.append(f"{n} áudio" + ("s" if n != 1 else ""))
    return " · ".join(partes)


def _titulos_dvdvideo(caminho: Path, disco: str, ff: FFmpeg, relatar: Relatar) -> list[Titulo]:
    titulos = []
    for n in range(1, MAX_TITULOS_DVD + 1):
        relatar(f"Lendo {disco}: título {n}...")
        entrada = ["-f", "dvdvideo", "-title", str(n), "-i", str(caminho)]
        info = ff.sondar(entrada)
        if info is None:
            break
        titulos.append(Titulo(disco, f"Título {n:02d}", entrada, _duracao(info), "DVD-Video", _resumo(info)))
    return titulos


def _titulo_de_arquivos(item: Item, ff: FFmpeg) -> Titulo | None:
    infos = [ff.sondar([*ENTRADA_TOLERANTE, "-i", str(c)]) for c in item.caminhos]
    primeiro = infos[0]
    if primeiro is None or not _streams(primeiro, "video"):
        return None
    caminhos = [str(c) for c in item.caminhos]
    entrada = [*ENTRADA_TOLERANTE, "-i", caminhos[0] if len(caminhos) == 1 else "concat:" + "|".join(caminhos)]
    duracao = _duracao(primeiro)
    if len(caminhos) > 1:
        # VOB dividido em 1 GB é um fluxo contínuo: a duração do concat é exata. Se o
        # relógio reiniciar entre as partes, o concat só enxerga um pedaço; aí vale a soma.
        soma = sum(_duracao(i) for i in infos)
        continua = _duracao(ff.sondar(entrada))
        duracao = continua if continua >= 0.9 * soma else soma
    tipo = TIPOS_POR_EXTENSAO.get(item.caminhos[0].suffix.lower(), "Vídeo")
    return Titulo(item.disco, item.nome, entrada, duracao, tipo, _resumo(primeiro))


def _titulos_de_vobs(pasta: Path, disco: str, ff: FFmpeg) -> list[Titulo]:
    grupos = agrupar_arquivos(p for p in pasta.iterdir() if p.is_file())
    candidatos = (_titulo_de_arquivos(Item("arquivos", disco, nome, tuple(g)), ff) for nome, g in grupos)
    return [t for t in candidatos if t]


def _sondar_item(item: Item, ff: FFmpeg, relatar: Relatar, dicas: list[str]) -> list[Titulo]:
    if item.tipo == "arquivos":
        titulo = _titulo_de_arquivos(item, ff)
        return [titulo] if titulo else []
    caminho = item.caminhos[0]
    titulos = _titulos_dvdvideo(caminho, item.disco, ff, relatar)
    if titulos:
        return titulos
    if item.tipo == "iso":
        dicas.append(
            f"A imagem {caminho.name} não abriu como DVD. Dê dois cliques nela no Explorer "
            "(o Windows a monta como uma unidade) e escolha essa unidade no programa."
        )
        return []
    relatar(f"O IFO de {caminho} não abriu; convertendo os VOBs por titleset.")
    return _titulos_de_vobs(caminho, item.disco, ff)


def analisar(caminho: str | Path, ff: FFmpeg, relatar: Relatar | None = None) -> list[Titulo]:
    relatar = relatar or (lambda _msg: None)
    titulos: list[Titulo] = []
    dicas: list[str] = []
    for item in planejar(caminho):
        titulos += _sondar_item(item, ff, relatar, dicas)
    if not titulos:
        # A dica vai junto na exceção: como status, ela seria apagada pelo aviso de erro.
        raise ErroFonte("\n\n".join([f"Nenhum vídeo de DVD encontrado em {caminho}", *dicas]))
    return titulos


# --- escolha ----------------------------------------------------------------------------

def ler_lista_numeros(texto: str) -> list[int]:
    """"1,3-5" -> [1, 3, 4, 5]"""
    numeros: list[int] = []
    for parte in filter(None, (p.strip() for p in texto.split(","))):
        inicio, _, fim = parte.partition("-")
        if not inicio.isdigit() or (fim and not fim.isdigit()):
            raise ValueError(f"Número de título inválido: {parte!r}")
        numeros += range(int(inicio), int(fim or inicio) + 1)
    return numeros


def selecionar(
    titulos: list[Titulo], minimo: float = 10.0, numeros: list[int] | None = None, so_maior: bool = False
) -> list[Titulo]:
    """Números são as posições da listagem (1 = primeiro). Sem números, descarta vinhetas curtas."""
    if numeros:
        fora = [n for n in numeros if not 1 <= n <= len(titulos)]
        if fora:
            raise ValueError(f"Título inexistente: {fora} (há {len(titulos)})")
        return [titulos[n - 1] for n in numeros]
    if so_maior:
        return [max(titulos, key=lambda t: t.duracao)]
    # Duração 0 = desconhecida: na dúvida, converte. Disco só de clipes curtos: todos.
    longos = [t for t in titulos if t.duracao == 0 or t.duracao >= minimo]
    return longos or list(titulos)


def unidades_de_dvd() -> list[str]:
    """Unidades de CD/DVD com disco inserido (só Windows)."""
    if os.name != "nt":
        return []
    import ctypes
    import string

    unidade_cdrom = 5
    tipo = ctypes.windll.kernel32.GetDriveTypeW
    return [f"{L}:\\" for L in string.ascii_uppercase if tipo(f"{L}:\\") == unidade_cdrom and os.path.isdir(f"{L}:\\")]
