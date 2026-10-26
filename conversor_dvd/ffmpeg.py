"""Localiza e executa o ffmpeg/ffprobe."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable

# Sem isso, cada chamada abre uma janela de console quando o programa roda pelo pythonw.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def pastas_locais() -> list[Path]:
    """ffmpeg/ ao lado do programa: da pasta do código ou da pasta do .exe instalado."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return [base / "ffmpeg" / "bin", base / "ffmpeg"]


class FFmpegAusente(RuntimeError):
    pass


@dataclass
class Resultado:
    codigo: int
    interrompido: bool
    erros: list[str]


def ler_progresso(linha: str) -> float | None:
    """Segundos já convertidos, a partir de uma linha do `-progress` do ffmpeg."""
    chave, _, valor = linha.strip().partition("=")
    # out_time_ms também vem em microssegundos (bug histórico do ffmpeg).
    if chave not in ("out_time_us", "out_time_ms") or not valor.lstrip("-").isdigit():
        return None
    return int(valor) / 1_000_000


def _achar(nome: str) -> str | None:
    exe = nome + (".exe" if os.name == "nt" else "")
    for pasta in pastas_locais():
        if (pasta / exe).is_file():
            return str(pasta / exe)
    return shutil.which(nome)


class FFmpeg:
    def __init__(self, ffmpeg: str, ffprobe: str) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    @classmethod
    def localizar(cls) -> FFmpeg:
        ffmpeg, ffprobe = _achar("ffmpeg"), _achar("ffprobe")
        if not ffmpeg or not ffprobe:
            raise FFmpegAusente(
                "FFmpeg não encontrado. Instale com:  winget install Gyan.FFmpeg\n"
                "ou copie ffmpeg.exe e ffprobe.exe para a pasta 'ffmpeg' ao lado do programa."
            )
        return cls(ffmpeg, ffprobe)

    @cached_property
    def tem_xvid(self) -> bool:
        saida = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, errors="replace", creationflags=SEM_JANELA,
        ).stdout
        return " libxvid " in saida

    def sondar(self, entrada: list[str]) -> dict | None:
        """ffprobe da entrada (já com as opções de entrada e o -i). None se não abrir."""
        r = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-show_format", "-show_streams", "-of", "json", *entrada],
            capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA,
        )
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except ValueError:
            return None

    def executar(
        self,
        cmd: list[str],
        duracao: float,
        ao_progredir: Callable[[float], None] | None = None,
        cancelado: Callable[[], bool] | None = None,
    ) -> Resultado:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA,
        )
        erros: deque[str] = deque(maxlen=40)
        linhas: queue.Queue[str | None] = queue.Queue()

        def ler_saida() -> None:
            for linha in proc.stdout:
                linhas.put(linha)
            linhas.put(None)

        # Leitura em threads: o laço principal consulta o cancelamento mesmo quando o
        # ffmpeg para de imprimir progresso (disco com setor ruim, por exemplo).
        leitores = [
            threading.Thread(target=ler_saida, daemon=True),
            threading.Thread(target=erros.extend, args=(proc.stderr,), daemon=True),
        ]
        for leitor in leitores:
            leitor.start()
        interrompido = terminou = False
        try:
            while True:
                if cancelado and cancelado():
                    interrompido = True
                    break
                try:
                    linha = linhas.get(timeout=0.2)
                except queue.Empty:
                    continue
                if linha is None:  # saída fechada: o ffmpeg terminou de gravar
                    terminou = True
                    break
                segundos = ler_progresso(linha)
                if segundos is not None and duracao > 0 and ao_progredir:
                    ao_progredir(min(segundos / duracao, 1.0))
        finally:
            # Só mata se ainda está rodando e não chegou ao fim: matar durante a
            # finalização do arquivo deixaria o MP4 sem o índice final.
            if not terminou and proc.poll() is None:
                proc.kill()
            proc.wait()
            for leitor in leitores:
                leitor.join(timeout=5)
        return Resultado(proc.returncode, interrompido, [e.rstrip() for e in erros if e.strip()])
