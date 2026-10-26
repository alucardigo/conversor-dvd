# -*- mode: python ; coding: utf-8 -*-
# Gera dist\ConversorDVD\: ConversorDVD.exe (janela) e conversor-dvd.exe (linha de comando).
# Uso (a partir da raiz do repositório): python -m PyInstaller packaging\ConversorDVD.spec --noconfirm
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, os.pardir))
ICONE = os.path.join(SPECPATH, "icone.ico")
EXCLUIDOS = ["pytest", "unittest", "pydoc", "_pytest"]

analise_janela = Analysis(
    [os.path.join(SPECPATH, "launcher_gui.py")],
    pathex=[RAIZ],
    excludes=EXCLUIDOS,
)
analise_cli = Analysis(
    [os.path.join(SPECPATH, "launcher_cli.py")],
    pathex=[RAIZ],
    excludes=EXCLUIDOS,
)
MERGE(
    (analise_janela, "ConversorDVD", "ConversorDVD"),
    (analise_cli, "conversor-dvd", "conversor-dvd"),
)

pyz = PYZ(analise_janela.pure)

exe_janela = EXE(
    pyz,
    analise_janela.scripts,
    [],
    exclude_binaries=True,
    name="ConversorDVD",
    icon=ICONE,
    console=False,
)
exe_cli = EXE(
    pyz,
    analise_cli.scripts,
    [],
    exclude_binaries=True,
    name="conversor-dvd",
    icon=ICONE,
    console=True,
)
COLLECT(
    exe_janela,
    analise_janela.binaries,
    analise_janela.datas,
    exe_cli,
    analise_cli.binaries,
    analise_cli.datas,
    name="ConversorDVD",
)
