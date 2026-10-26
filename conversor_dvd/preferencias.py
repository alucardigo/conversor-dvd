"""Pasta de dados do programa: preferências da janela e registro de erros.

Fica em %APPDATA%\\ConversorDVD. Nada aqui pode impedir uma conversão: as leituras e
gravações falham em silêncio.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def pasta_dados() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ConversorDVD"


def carregar(caminho: Path | None = None) -> dict:
    """Preferências salvas, ou {} se o arquivo não existe ou está corrompido."""
    try:
        dados = json.loads((caminho or pasta_dados() / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def salvar(dados: dict, caminho: Path | None = None) -> None:
    destino = caminho or pasta_dados() / "config.json"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def registrar_erro(texto: str, caminho: Path | None = None) -> Path:
    """Anota um erro inesperado em erros.log e devolve o caminho para mostrar ao usuário."""
    destino = caminho or pasta_dados() / "erros.log"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as arq:
            arq.write(f"--- {datetime.now():%d/%m/%Y %H:%M:%S}\n{texto}\n")
    except OSError:
        pass
    return destino
