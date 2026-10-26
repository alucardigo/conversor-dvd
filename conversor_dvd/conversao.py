"""Monta e executa a conversão de um título para MP4 ou AVI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .ffmpeg import FFmpeg
from .fontes import Titulo, nome_seguro

FORMATOS = ("mp4", "avi")

# Só desentrelaça quadro marcado como entrelaçado: filme progressivo passa intacto.
DESENTRELACAR = "bwdif=mode=send_frame:parity=auto:deint=interlaced"
# DVD guarda 720 pixels "esticados" (4:3 ou 16:9). MP4 carrega a proporção; AVI em
# aparelho antigo costuma ignorá-la, então lá o pixel vira quadrado de verdade.
PIXEL_QUADRADO = "scale=trunc(iw*sar/2)*2:ih,setsar=1"


@dataclass(frozen=True)
class Perfil:
    crf: int  # H.264: menor = melhor
    xvid_q: int  # Xvid: 2 (ótimo) a 31
    audio: str


# Xvid medido num DVD de filmadora antigo (60 s, SSIM contra a fonte): q3 4,2 Mbps
# 0,987 · q4 2,9 Mbps 0,983 · q6 1,9 Mbps 0,975. q2 quase não comprime o DVD.
PERFIS = {
    "alta": Perfil(crf=18, xvid_q=3, audio="192k"),
    "media": Perfil(crf=21, xvid_q=4, audio="160k"),
    "pequena": Perfil(crf=24, xvid_q=6, audio="128k"),
}


@dataclass(frozen=True)
class Opcoes:
    qualidade: str = "media"
    desentrelacar: bool = True

    def __post_init__(self) -> None:
        if self.qualidade not in PERFIS:
            raise ValueError(f"Qualidade inválida: {self.qualidade!r} (use {', '.join(PERFIS)})")


class ErroConversao(RuntimeError):
    pass


class Cancelado(Exception):
    pass


def pasta_padrao() -> Path:
    return Path.home() / "Videos" / "DVDs convertidos"


def formatar_duracao(segundos: float) -> str:
    if segundos <= 0:
        return "?"
    h, resto = divmod(int(segundos), 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def nome_unico(alvo: Path) -> Path:
    n, candidato = 2, alvo
    while candidato.exists():
        candidato = alvo.with_name(f"{alvo.stem} ({n}){alvo.suffix}")
        n += 1
    return candidato


def montar_comando(ffmpeg: str, titulo: Titulo, formato: str, saida: Path, opcoes: Opcoes, xvid: bool = True) -> list[str]:
    if formato not in FORMATOS:
        raise ValueError(f"Formato inválido: {formato!r} (use {' ou '.join(FORMATOS)})")
    perfil = PERFIS[opcoes.qualidade]
    filtros = [DESENTRELACAR] if opcoes.desentrelacar else []
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *titulo.entrada]
    if formato == "mp4":
        cmd += ["-map", "0:v:0", "-map", "0:a?"]  # todas as faixas de áudio (dublado + original)
        cmd += ["-vf", ",".join(filtros)] if filtros else []
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(perfil.crf), "-pix_fmt", "yuv420p"]
        cmd += ["-c:a", "aac", "-b:a", perfil.audio, "-movflags", "+faststart"]
    else:
        filtros.append(PIXEL_QUADRADO)
        cmd += ["-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filtros)]  # AVI: uma faixa só
        cmd += ["-c:v", "libxvid" if xvid else "mpeg4", "-q:v", str(perfil.xvid_q), "-vtag", "XVID"]
        cmd += ["-c:a", "libmp3lame", "-b:a", perfil.audio, "-ac", "2"]
    cmd += ["-sn", "-dn", "-max_muxing_queue_size", "4096", "-metadata", f"title={titulo.rotulo}", str(saida)]
    return cmd


def converter(
    ff: FFmpeg,
    titulo: Titulo,
    formato: str,
    pasta: Path,
    opcoes: Opcoes,
    ao_progredir: Callable[[float], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Path:
    """Converte um título. Grava em '<nome>.parcial.<ext>' e só renomeia se der certo."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    final = nome_unico(pasta / f"{nome_seguro(titulo.rotulo)}.{formato}")
    parcial = final.with_name(f"{final.stem}.parcial{final.suffix}")
    if cancelado and cancelado():
        raise Cancelado()
    cmd = montar_comando(ff.ffmpeg, titulo, formato, parcial, opcoes, xvid=ff.tem_xvid)
    pronto = False
    try:
        r = ff.executar(cmd, titulo.duracao, ao_progredir, cancelado)
        if r.interrompido:
            raise Cancelado()
        if r.codigo != 0 or not parcial.exists():
            detalhe = "\n".join(r.erros[-6:]) or f"ffmpeg saiu com código {r.codigo}"
            raise ErroConversao(f"Falhou ao converter {titulo.rotulo} para {formato.upper()}:\n{detalhe}")
        parcial.replace(final)
        pronto = True
    finally:
        if not pronto:
            parcial.unlink(missing_ok=True)
    if ao_progredir:
        ao_progredir(1.0)
    return final
