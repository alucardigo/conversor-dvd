"""Janela do Conversor de DVD (tkinter: já vem com o Python, sem instalar nada)."""
from __future__ import annotations

import os
import queue
import threading
import time
import traceback
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import preferencias
from .conversao import FORMATOS, Cancelado, ErroConversao, Opcoes, converter, formatar_duracao, pasta_padrao
from .ffmpeg import FFmpeg, FFmpegAusente
from .fontes import ErroFonte, Titulo, analisar, selecionar, unidades_de_dvd

TITULO_JANELA = "Conversor de DVD"
MINIMO_SEGUNDOS = 10  # títulos menores (vinhetas, logos) começam desmarcados
QUALIDADES = (("alta", "Alta (arquivo maior)"), ("media", "Média (recomendada)"), ("pequena", "Pequena (arquivo menor)"))
NOMES_FORMATO = {"mp4": "MP4 (TV, celular e PC)", "avi": "AVI (aparelhos antigos)"}
MARCADO, LIVRE = "☑", "☐"
TIPOS_DE_ARQUIVO = [
    ("Discos e vídeos de DVD", "*.iso *.img *.ifo *.vob *.vro *.mpg *.mpeg *.dat *.mod *.tod *.mts *.m2ts *.m2v *.ts"),
    ("Todos os arquivos", "*.*"),
]


@dataclass
class Balanco:
    """Resultado de um lote de conversões, entregue pela thread de trabalho à janela."""
    total: int = 0
    destino: Path = field(default_factory=Path)
    feitos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    cancelado: bool = False


def _prefs_validas(bruto: dict) -> dict:
    """Preferências lidas do disco podem estar editadas à mão: aceita só o que o programa entende."""
    formatos = [f for f in FORMATOS if f in bruto.get("formatos", ["mp4"])] or ["mp4"]
    qualidade = bruto.get("qualidade", "media")
    return {
        "destino": str(bruto.get("destino") or pasta_padrao()),
        "formatos": formatos,
        "qualidade": qualidade if qualidade in dict(QUALIDADES) else "media",
        "desentrelacar": bool(bruto.get("desentrelacar", True)),
    }


class Janela:
    def __init__(self, raiz: tk.Tk, ff: FFmpeg, minimo: float = MINIMO_SEGUNDOS) -> None:
        self.raiz, self.ff, self.minimo = raiz, ff, minimo
        prefs = _prefs_validas(preferencias.carregar())
        self.fila: queue.Queue = queue.Queue()
        self.titulos: list[Titulo] = []
        self.marcados: set[int] = set()
        self.cancelar = threading.Event()
        self.analisando = False
        self.convertendo = False
        self._fechando = False
        self._inicio = 0.0
        self._rotulo = ""
        self.ultimo_destino: Path | None = None

        self.origem = tk.StringVar(value=next(iter(unidades_de_dvd()), ""))
        self.destino = tk.StringVar(value=prefs["destino"])
        self.formatos = {f: tk.BooleanVar(value=f in prefs["formatos"]) for f in FORMATOS}
        self.qualidade = tk.StringVar(value=prefs["qualidade"])
        self.desentrelacar = tk.BooleanVar(value=prefs["desentrelacar"])
        self.resumo = tk.StringVar(value="Coloque o DVD na unidade, ou escolha uma pasta ou um arquivo, e clique em Analisar disco.")
        self.progresso = tk.DoubleVar(value=0.0)

        self._tratadores = {
            "status": self.resumo.set,
            "rotulo": self._definir_rotulo,
            "titulos": self._mostrar_titulos,
            "erro_fonte": self._mostrar_erro_fonte,
            "erro_inesperado": self._erro_inesperado,
            "indeterminado": self._indeterminado,
            "progresso": self._mostrar_progresso,
            "fim": self._terminar,
        }
        raiz.title(TITULO_JANELA)
        raiz.minsize(900, 660)
        raiz.protocol("WM_DELETE_WINDOW", self._fechar)
        raiz.report_callback_exception = _excecao_na_tela
        self._estilo()
        self._montar()
        self._estado()
        raiz.after(100, self._processar_fila)

    # --- tela -----------------------------------------------------------------------

    def _estilo(self) -> None:
        estilo = ttk.Style(self.raiz)
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"))
        estilo.configure("Dica.TLabel", foreground="#555555")

    def _montar(self) -> None:
        corpo = ttk.Frame(self.raiz, padding=(16, 12))
        corpo.pack(fill="both", expand=True)
        corpo.columnconfigure(0, weight=1)
        corpo.rowconfigure(3, weight=1)

        ttk.Label(corpo, text="Conversor de DVD", style="Titulo.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(corpo, text="Converte DVDs antigos para MP4 ou AVI.", style="Dica.TLabel").grid(
            row=1, column=0, sticky="w", pady=(0, 6))

        self._montar_origem(corpo).grid(row=2, column=0, sticky="ew", pady=4)
        self._montar_titulos(corpo).grid(row=3, column=0, sticky="nsew", pady=4)
        self._montar_opcoes(corpo).grid(row=4, column=0, sticky="ew", pady=4)

        acoes = ttk.Frame(corpo)
        acoes.grid(row=5, column=0, sticky="ew", pady=(8, 4))
        self.bt_converter = ttk.Button(acoes, text="Converter", command=self._converter)
        self.bt_converter.pack(side="left")
        self.bt_cancelar = ttk.Button(acoes, text="Cancelar", command=self._pedir_cancelamento)
        self.bt_cancelar.pack(side="left", padx=6)
        self.bt_abrir = ttk.Button(acoes, text="Abrir pasta com os vídeos", command=self._abrir_destino)
        self.bt_abrir.pack(side="right")

        progresso = ttk.Frame(corpo)
        progresso.grid(row=6, column=0, sticky="ew")
        progresso.columnconfigure(0, weight=1)
        self.barra = ttk.Progressbar(progresso, variable=self.progresso, maximum=1.0)
        self.barra.grid(row=0, column=0, sticky="ew")
        ttk.Label(progresso, textvariable=self.resumo).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _montar_origem(self, pai: ttk.Frame) -> ttk.LabelFrame:
        quadro = ttk.LabelFrame(pai, text=" 1. De onde vem o DVD? ", padding=10)
        quadro.columnconfigure(0, weight=1)
        self.cb_origem = ttk.Combobox(quadro, textvariable=self.origem, values=unidades_de_dvd())
        self.cb_origem.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cb_origem.bind("<Return>", lambda _e: self._analisar())
        botoes = ttk.Frame(quadro)
        botoes.grid(row=0, column=1, sticky="e")
        ttk.Button(botoes, text="Atualizar unidades", command=self._atualizar_unidades).pack(side="left")
        ttk.Button(botoes, text="Pasta...", command=self._escolher_pasta).pack(side="left", padx=4)
        ttk.Button(botoes, text="Arquivo...", command=self._escolher_arquivo).pack(side="left")
        self.bt_analisar = ttk.Button(botoes, text="Analisar disco", command=self._analisar)
        self.bt_analisar.pack(side="left", padx=(12, 0))
        ttk.Label(quadro, text="Unidade com o DVD, pasta com o conteúdo do disco, imagem ISO ou arquivo de vídeo.",
                  style="Dica.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        return quadro

    def _montar_titulos(self, pai: ttk.Frame) -> ttk.LabelFrame:
        quadro = ttk.LabelFrame(pai, text=" 2. Quais títulos converter? ", padding=10)
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(0, weight=1)
        colunas = (("marca", "Converter", 80, "center"), ("n", "#", 40, "e"), ("titulo", "Disco e título", 260, "w"),
                   ("duracao", "Duração", 80, "e"), ("tipo", "Tipo", 100, "w"), ("info", "Detalhes", 220, "w"))
        self.lista = ttk.Treeview(quadro, columns=[c[0] for c in colunas], show="headings", selectmode="browse", height=7)
        for chave, texto, largura, ancora in colunas:
            self.lista.heading(chave, text=texto)
            self.lista.column(chave, width=largura, anchor=ancora, stretch=chave in ("titulo", "info"))
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=rolagem.set)
        self.lista.grid(row=0, column=0, sticky="nsew")
        rolagem.grid(row=0, column=1, sticky="ns")
        self.lista.bind("<Button-1>", self._clicou_na_lista)
        self.lista.bind("<space>", self._espaco_na_lista)

        barra = ttk.Frame(quadro)
        barra.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(barra, text="Marcar todos", command=lambda: self._marcar_todos(True)).pack(side="left")
        ttk.Button(barra, text="Desmarcar todos", command=lambda: self._marcar_todos(False)).pack(side="left", padx=4)
        ttk.Label(barra, text=f"Clique na caixinha ou aperte espaço. Títulos com menos de {MINIMO_SEGUNDOS} s começam desmarcados.",
                  style="Dica.TLabel").pack(side="left", padx=12)
        return quadro

    def _montar_opcoes(self, pai: ttk.Frame) -> ttk.LabelFrame:
        quadro = ttk.LabelFrame(pai, text=" 3. Como salvar? ", padding=10)
        linha1 = ttk.Frame(quadro)
        linha1.pack(fill="x")
        ttk.Label(linha1, text="Formato:").pack(side="left")
        for formato in FORMATOS:
            ttk.Checkbutton(linha1, text=NOMES_FORMATO[formato], variable=self.formatos[formato],
                            command=self._estado).pack(side="left", padx=(8, 0))
        ttk.Label(linha1, text="    Qualidade:").pack(side="left")
        for valor, texto in QUALIDADES:
            ttk.Radiobutton(linha1, text=texto, value=valor, variable=self.qualidade).pack(side="left", padx=(6, 0))

        linha2 = ttk.Frame(quadro)
        linha2.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(linha2, text="Remover serrilhado (recomendado para DVD)",
                        variable=self.desentrelacar).pack(side="left")

        linha3 = ttk.Frame(quadro)
        linha3.pack(fill="x", pady=(8, 0))
        ttk.Label(linha3, text="Salvar em:").pack(side="left")
        ttk.Entry(linha3, textvariable=self.destino).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(linha3, text="Escolher...", command=self._escolher_destino).pack(side="left")
        return quadro

    # --- seleção de títulos -----------------------------------------------------------

    def _clicou_na_lista(self, evento: tk.Event) -> None:
        if self.lista.identify_region(evento.x, evento.y) != "cell" or self.lista.identify_column(evento.x) != "#1":
            return
        iid = self.lista.identify_row(evento.y)
        if iid:
            self._alternar(iid)

    def _espaco_na_lista(self, _evento: tk.Event) -> str:
        iid = self.lista.focus()
        if iid:
            self._alternar(iid)
        return "break"

    def _alternar(self, iid: str) -> None:
        i = int(iid)
        self.marcados.symmetric_difference_update({i})
        self.lista.set(iid, "marca", MARCADO if i in self.marcados else LIVRE)
        self._estado()

    def _marcar_todos(self, valor: bool) -> None:
        self.marcados = set(range(len(self.titulos))) if valor else set()
        for i in range(len(self.titulos)):
            self.lista.set(str(i), "marca", MARCADO if valor else LIVRE)
        self._estado()

    # --- ações ----------------------------------------------------------------------

    def _atualizar_unidades(self) -> None:
        unidades = unidades_de_dvd()
        self.cb_origem.configure(values=unidades)
        if unidades and not self.origem.get().strip():
            self.origem.set(unidades[0])
        if not unidades:
            self.resumo.set("Nenhum DVD encontrado nas unidades. Coloque o disco ou escolha uma pasta ou um arquivo.")

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Unidade do DVD ou pasta com o conteúdo do disco", parent=self.raiz)
        if pasta:
            self.origem.set(os.path.normpath(pasta))

    def _escolher_arquivo(self) -> None:
        arquivo = filedialog.askopenfilename(title="Imagem ISO ou arquivo de vídeo do DVD",
                                             filetypes=TIPOS_DE_ARQUIVO, parent=self.raiz)
        if arquivo:
            self.origem.set(os.path.normpath(arquivo))

    def _escolher_destino(self) -> None:
        pasta = filedialog.askdirectory(title="Onde salvar os vídeos convertidos", parent=self.raiz)
        if pasta:
            self.destino.set(os.path.normpath(pasta))

    def _abrir_destino(self) -> None:
        if self.ultimo_destino and self.ultimo_destino.exists():
            os.startfile(self.ultimo_destino)  # noqa: S606 - pasta escolhida pelo próprio usuário

    def _analisar(self) -> None:
        if self.analisando or self.convertendo:
            return
        origem = self.origem.get().strip().strip('"')
        if not origem:
            messagebox.showinfo(TITULO_JANELA, "Escolha primeiro a unidade, a pasta ou o arquivo do DVD.", parent=self.raiz)
            return
        self.lista.delete(*self.lista.get_children())
        self.titulos, self.marcados = [], set()
        self.analisando = True
        self.resumo.set("Lendo o disco... isso pode levar alguns segundos.")
        self._estado()
        threading.Thread(target=self._tarefa_analise, args=(origem,), daemon=True).start()

    def _tarefa_analise(self, origem: str) -> None:
        try:
            titulos = analisar(origem, self.ff, relatar=lambda msg: self.fila.put(("status", msg)))
        except ErroFonte as e:
            self.fila.put(("erro_fonte", str(e)))
        except Exception:
            self.fila.put(("erro_inesperado", traceback.format_exc()))
        else:
            self.fila.put(("titulos", titulos))

    def _converter(self) -> None:
        if self.analisando or self.convertendo:
            return
        escolhidos = [self.titulos[i] for i in sorted(self.marcados)]
        formatos = [f for f in FORMATOS if self.formatos[f].get()]
        destino = Path(self.destino.get().strip() or pasta_padrao())
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror(TITULO_JANELA, f"Não consegui criar a pasta:\n{destino}\n\n{e}", parent=self.raiz)
            return
        self._salvar_preferencias()
        tarefas = [(t, f) for t in escolhidos for f in formatos]
        self.cancelar.clear()
        self.convertendo = True
        self._fechando = False
        self._inicio = time.monotonic()
        self.ultimo_destino = None
        self.progresso.set(0.0)
        self._estado()
        opcoes = Opcoes(self.qualidade.get(), self.desentrelacar.get())
        threading.Thread(target=self._executar, args=(tarefas, destino, opcoes), daemon=True).start()

    def _executar(self, tarefas: list[tuple[Titulo, str]], destino: Path, opcoes: Opcoes) -> None:
        """Roda fora da thread da tela: só conversa com ela pela fila."""
        total = len(tarefas)
        balanco = Balanco(total=total, destino=destino)
        try:
            for i, (titulo, formato) in enumerate(tarefas):
                if self.cancelar.is_set():
                    balanco.cancelado = True
                    break
                self.fila.put(("rotulo", f"{i + 1} de {total}: {titulo.rotulo} → {formato.upper()}"))
                self.fila.put(("indeterminado", titulo.duracao <= 0))
                try:
                    saida = converter(
                        self.ff, titulo, formato, destino, opcoes,
                        ao_progredir=lambda x, i=i: self.fila.put(("progresso", (i + x) / total)),
                        cancelado=self.cancelar.is_set,
                    )
                except Cancelado:
                    balanco.cancelado = True
                    break
                except ErroConversao as e:
                    balanco.erros.append(str(e))
                except Exception:  # a thread nunca pode morrer sem avisar a janela
                    balanco.erros.append(f"Erro inesperado em {titulo.rotulo}. Detalhes em erros.log.")
                    preferencias.registrar_erro(traceback.format_exc())
                else:
                    balanco.feitos.append(str(saida))
        except Exception:
            balanco.erros.append("Erro inesperado. Detalhes em erros.log.")
            preferencias.registrar_erro(traceback.format_exc())
        finally:
            self.fila.put(("fim", balanco))

    def _pedir_cancelamento(self) -> None:
        self.cancelar.set()
        self.bt_cancelar.state(["disabled"])
        self.resumo.set("Cancelando...")

    def _fechar(self) -> None:
        if self.convertendo:
            if not messagebox.askyesno(TITULO_JANELA, "Há uma conversão em andamento. Cancelar e sair?", parent=self.raiz):
                return
            self._fechando = True
            self._pedir_cancelamento()
            self._salvar_preferencias()
            self._esperar_e_sair()
            return
        self._salvar_preferencias()
        self.raiz.destroy()

    def _esperar_e_sair(self) -> None:
        # O ffmpeg é morto e o arquivo parcial apagado antes de a janela fechar.
        if self.convertendo:
            self.raiz.after(200, self._esperar_e_sair)
        else:
            self.raiz.destroy()

    def _salvar_preferencias(self) -> None:
        preferencias.salvar({
            "destino": self.destino.get().strip(),
            "formatos": [f for f in FORMATOS if self.formatos[f].get()],
            "qualidade": self.qualidade.get(),
            "desentrelacar": self.desentrelacar.get(),
        })

    # --- comunicação com as threads ---------------------------------------------------

    def _processar_fila(self) -> None:
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                self._tratadores[tipo](dado)
        except queue.Empty:
            pass
        self.raiz.after(100, self._processar_fila)

    def _mostrar_titulos(self, titulos: list[Titulo]) -> None:
        self.analisando = False
        self.titulos = titulos
        sugeridos = {id(t) for t in selecionar(titulos, self.minimo)}
        self.marcados = {i for i, t in enumerate(titulos) if id(t) in sugeridos}
        self.lista.delete(*self.lista.get_children())
        for i, t in enumerate(titulos):
            self.lista.insert("", "end", iid=str(i), values=(
                MARCADO if i in self.marcados else LIVRE, i + 1, t.rotulo,
                formatar_duracao(t.duracao), t.tipo, t.info))
        total = sum(t.duracao for t in titulos)
        self.resumo.set(f"{len(titulos)} título(s), {formatar_duracao(total)} no total. Marque o que quer converter.")
        self._estado()

    def _mostrar_erro_fonte(self, mensagem: str) -> None:
        self.analisando = False
        self.resumo.set("Não foi possível usar esta origem.")
        self._estado()
        messagebox.showwarning(TITULO_JANELA, mensagem, parent=self.raiz)

    def _erro_inesperado(self, texto: str) -> None:
        self.analisando = False
        caminho = preferencias.registrar_erro(texto)
        self.resumo.set("Algo inesperado aconteceu. Veja a mensagem.")
        self._estado()
        messagebox.showerror(TITULO_JANELA, f"Algo inesperado aconteceu e a operação foi interrompida.\n\nDetalhes salvos em:\n{caminho}", parent=self.raiz)

    def _definir_rotulo(self, texto: str) -> None:
        self._rotulo = texto
        self.resumo.set(texto)

    def _indeterminado(self, ativo: bool) -> None:
        if ativo:
            self.barra.configure(mode="indeterminate")
            self.barra.start(15)
            self.resumo.set(f"{self._rotulo}  (aguarde...)")
        else:
            self.barra.stop()
            self.barra.configure(mode="determinate")

    def _mostrar_progresso(self, fracao: float) -> None:
        self.progresso.set(fracao)
        tempo = ""
        if fracao >= 0.02:
            restante = (time.monotonic() - self._inicio) * (1 - fracao) / fracao
            tempo = f"  ·  faltam cerca de {formatar_duracao(restante)}"
        self.resumo.set(f"{self._rotulo}  ({fracao:.0%}){tempo}")

    def _terminar(self, balanco: Balanco) -> None:
        self.convertendo = False
        self._indeterminado(False)
        feitos, total = len(balanco.feitos), balanco.total
        self.ultimo_destino = balanco.destino if feitos else None
        if balanco.cancelado:
            self.resumo.set(f"Cancelado. {feitos} de {total} arquivo(s) ficaram prontos.")
        elif balanco.erros:
            self.resumo.set(f"Terminou com problemas: {feitos} de {total} arquivo(s) criados.")
        else:
            self.progresso.set(1.0)
            self.resumo.set(f"Pronto! {feitos} arquivo(s) criados em {balanco.destino}")
        self._estado()
        if balanco.erros and not self._fechando:
            resto = "\n\n..." if len(balanco.erros) > 3 else ""
            messagebox.showwarning(TITULO_JANELA, "Estes arquivos não foram criados:\n\n" + "\n\n".join(balanco.erros[:3]) + resto,
                                   parent=self.raiz)

    def _estado(self) -> None:
        ocupado = self.analisando or self.convertendo
        pode_converter = not ocupado and bool(self.marcados) and any(v.get() for v in self.formatos.values())
        self.bt_analisar.state(["disabled"] if ocupado else ["!disabled"])
        self.bt_converter.state(["!disabled"] if pode_converter else ["disabled"])
        self.bt_cancelar.state(["!disabled"] if self.convertendo and not self.cancelar.is_set() else ["disabled"])
        self.bt_abrir.state(["!disabled"] if self.ultimo_destino else ["disabled"])


def _excecao_na_tela(exc: type[BaseException], valor: BaseException, tb) -> None:
    """Rede de segurança: qualquer erro num retorno de chamada vira aviso e registro, sem travar a janela."""
    caminho = preferencias.registrar_erro("".join(traceback.format_exception(exc, valor, tb)))
    messagebox.showerror(TITULO_JANELA, f"Algo inesperado aconteceu.\n\nDetalhes salvos em:\n{caminho}")


def _nitidez_em_tela_hd() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main() -> None:
    _nitidez_em_tela_hd()
    raiz = tk.Tk()
    try:
        ff = FFmpeg.localizar()
    except FFmpegAusente as e:
        raiz.withdraw()
        messagebox.showerror(TITULO_JANELA, str(e))
        raiz.destroy()
        return
    Janela(raiz, ff)
    raiz.mainloop()


if __name__ == "__main__":
    main()
