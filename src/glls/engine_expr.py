"""Le espressioni del motore: il linguaggio di ``maps:`` (PGE #308, #313).

Uno stream engine puo' dichiarare delle mappe iterate (``maps: {m1: {type:
logistic, r: 3.5}}``) e leggerle con un'espressione fra parentesi, valutata
**a ogni grano**: ``grain.duration: (0.02 + 0.08*m1)``. Non e' il linguaggio
dei nodi-expr degli studi (``exprlang``): quelli sono dict ``{expr: ...}``
risolti quando lo studio si espande, con i nomi di ``let:`` e ``i``/``n``;
queste sono stringhe che attraversano lo studio intatte e arrivano al motore,
con i nomi delle mappe e ``t``. Due linguaggi, due momenti, e qui non si
mescolano: un nodo-expr e' un dict, un'espressione del motore una stringa.

Mirror di ``pge/expressions/expression.py`` (l'interprete, senza ``eval``),
``pge/expressions/fields.py`` (dove un'espressione vale e dove no) e
``pge/engine/expression_shelter.py`` (``LOAD_TIME_NAMES``). gl-ls non importa
il motore: replica la grammatica e i nomi, e qui serve solo a dire *se* un
testo compila, e che cosa legge. Le chiusure non servono.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Il linguaggio

#: nome -> (argomenti minimi, massimi; None = quanti si vuole). Lo stesso
#: elenco, nello stesso ordine, di ``FUNCTIONS`` del motore.
FUNCTIONS: Dict[str, Tuple[int, Optional[int]]] = {
    "sin": (1, 1), "cos": (1, 1), "tan": (1, 1), "abs": (1, 1),
    "sqrt": (1, 1), "exp": (1, 1), "log": (1, 1), "floor": (1, 1),
    "round": (1, 1), "sign": (1, 1), "min": (1, None), "max": (1, None),
    "pow": (2, 2), "frac": (1, 1), "clip": (3, 3), "fold": (3, 3),
    "wrap": (3, 3),
}

#: Le costanti del linguaggio (``CONSTANTS``).
CONSTANTS = ("pi", "e")

#: Livelli di annidamento ammessi: parentesi, segni, potenze, chiamate
#: (``MAX_DEPTH``). Oltre e' un ``ExpressionError`` al caricamento.
MAX_DEPTH = 50

#: Il tempo, in secondi dall'inizio dello stream (``TIME_NAME``).
TIME_NAME = "t"

#: Le variabili dell'equazione di una mappa ``type: custom``
#: (``MAP_EQUATION_VARIABLES``).
MAP_EQUATION_VARIABLES = ("x", "y", "r")

#: Un nome: lettere, cifre e ``_``, con al piu' un punto (``m1.y``).
NAME_PATTERN = r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?"

_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<numero>\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)"
    rf"|(?P<nome>{NAME_PATTERN})"
    r"|(?P<segno>\*\*|[-+*/(),])"
    r")"
)

#: I nomi che la valutazione al **caricamento** conosce
#: (``LOAD_TIME_NAMES``, le chiavi del ``safe_dict`` di
#: ``Generator._eval_math_expressions``). Una stringa fra parentesi che legge
#: solo questi il motore la valuta subito in una costante, in ogni campo.
LOAD_TIME_NAMES: FrozenSet[str] = frozenset({
    "abs", "int", "float", "min", "max", "pow", "pi", "e"})

#: Un nome dentro un testo, non un pezzo di numero (in ``1e3`` la ``e3`` non
#: e' un nome): il regex ``_NOMI`` del riparo.
_NOMI = re.compile(rf"(?<![A-Za-z_0-9.]){NAME_PATTERN}")

# ---------------------------------------------------------------------------
# Dove un'espressione vale

#: Il valore base di ogni parametro a schema (``EXPRESSION_FIELDS``, PGE
#: #313): path YAML dentro lo stream.
EXPRESSION_FIELDS: Tuple[str, ...] = (
    "grain.duration", "grain.iot", "pointer.position",
    "volume", "pan",
    "pitch.semitones", "pitch.cents", "pitch.quarter_tone",
    "pitch.eighth_tone", "pitch.ratio", "pitch.value",
    "density", "fill_factor", "distribution",
    "grain.read_direction",
)

#: Dove ci si aspetterebbe di poterla scrivere e il motore la rifiuta, con
#: che cosa scrivere al suo posto (``EXPRESSION_REFUSALS``).
_LOOP_EDGE = ("i bordi della finestra di loop sono numeri o envelope: la "
              "finestra e' il vincolo del puntatore. La mappa muove la "
              "posizione dentro la finestra, con pointer.position")
EXPRESSION_REFUSALS: Dict[str, str] = {
    "pointer.speed_ratio": (
        "la velocita' si integra nel tempo per ricavare la posizione, e "
        "un'espressione non si integra: per leggere la posizione da una "
        "mappa usa pointer.position"),
    "pointer.start": (
        "e' la posizione di partenza, un numero: per una posizione che "
        "cambia a ogni grano usa pointer.position"),
    "pointer.loop_start": _LOOP_EDGE,
    "pointer.loop_end": _LOOP_EDGE,
    "pointer.loop_dur": _LOOP_EDGE,
    "voices.num_voices": (
        "il numero di voci si decide prima dei grani (e' il picco del suo "
        "envelope): un numero o un envelope. Una mappa puo' muovere volume, "
        "pan e pitch, e ogni voce ha il suo stato"),
}

#: Il suggerimento degli altri campi che la rifiutano.
GENERIC_REFUSAL = ("un'espressione vale sul valore base di: "
                   + ", ".join(EXPRESSION_FIELDS))


# ---------------------------------------------------------------------------
# Compilazione (solo validazione)

@dataclass(frozen=True)
class Problem:
    """Perche' un testo non e' un'espressione del linguaggio."""
    reason: str
    hint: Optional[str] = None


class _Errore(Exception):
    def __init__(self, reason: str, hint: Optional[str] = None):
        super().__init__(reason)
        self.problem = Problem(reason, hint)


def _token(sorgente: str) -> List[Tuple[str, object]]:
    trovati: List[Tuple[str, object]] = []
    posizione = 0
    while posizione < len(sorgente):
        if not sorgente[posizione:].strip():
            break
        m = _TOKEN.match(sorgente, posizione)
        if not m:
            resto = sorgente[posizione:].strip()[:12]
            raise _Errore(f"non capisco «{resto}»")
        posizione = m.end()
        if m.group("numero") is not None:
            trovati.append(("n", float(m.group("numero"))))
        elif m.group("nome") is not None:
            trovati.append(("id", m.group("nome")))
        else:
            trovati.append((m.group("segno"), m.group("segno")))
    return trovati


def _argomenti_attesi(nome: str, minimo: int, massimo: Optional[int]) -> str:
    if massimo is None:
        return f"{nome} vuole almeno un argomento"
    return f"{nome} vuole {minimo} argoment{'o' if minimo == 1 else 'i'}"


class _Parser:
    """La discesa ricorsiva del motore, senza le chiusure."""

    def __init__(self, token, variabili):
        self._token = token
        self._p = 0
        self._variabili = variabili
        self.letti: List[str] = []
        self._profondita = 0

    def _scendi(self):
        self._profondita += 1
        if self._profondita > MAX_DEPTH:
            raise _Errore(
                f"e' annidata troppo: al piu' {MAX_DEPTH} livelli fra "
                "parentesi, segni, potenze e chiamate",
                hint="togli le parentesi e i segni che non servono: "
                     "((x)) e' x, --x e' x")

    def _tipo(self):
        return self._token[self._p][0] if self._p < len(self._token) else None

    def _vuole(self, tipo):
        if self._tipo() != tipo:
            raise _Errore("manca una parentesi chiusa" if tipo == ")"
                          else f"manca «{tipo}»")
        self._p += 1

    def tutto(self):
        self.espressione()
        if self._p < len(self._token):
            raise _Errore(f"non mi aspettavo «{self._mostra()}»")

    def _mostra(self):
        tipo, valore = self._token[self._p]
        return f"{valore:g}" if tipo == "n" else str(valore)

    def espressione(self):
        self.termine()
        while self._tipo() in ("+", "-"):
            self._p += 1
            self.termine()

    def termine(self):
        self.unario()
        while self._tipo() in ("*", "/"):
            self._p += 1
            self.unario()

    def unario(self):
        if self._tipo() in ("-", "+"):
            self._p += 1
            self._scendi()
            self.unario()
            self._profondita -= 1
            return
        self.potenza()

    def potenza(self):
        self.primario()
        if self._tipo() == "**":
            self._p += 1
            self._scendi()
            self.unario()
            self._profondita -= 1

    def primario(self):
        if self._p >= len(self._token):
            raise _Errore("finisce a meta'")
        tipo, valore = self._token[self._p]
        if tipo == "n":
            self._p += 1
            return
        if tipo == "(":
            self._p += 1
            self._scendi()
            self.espressione()
            self._vuole(")")
            self._profondita -= 1
            return
        if tipo == "id":
            self._p += 1
            if self._tipo() == "(":
                self._chiamata(valore)
            else:
                self._nome(valore)
            return
        raise _Errore(f"non mi aspettavo «{valore}»")

    def _chiamata(self, nome):
        if nome not in FUNCTIONS:
            raise _Errore(f"funzione sconosciuta «{nome}»",
                          hint=f"funzioni: {' '.join(FUNCTIONS)}")
        minimo, massimo = FUNCTIONS[nome]
        self._p += 1
        self._scendi()
        quanti = 0
        if self._tipo() != ")":
            self.espressione()
            quanti = 1
            while self._tipo() == ",":
                self._p += 1
                self.espressione()
                quanti += 1
        self._vuole(")")
        self._profondita -= 1
        if quanti < minimo or (massimo is not None and quanti > massimo):
            raise _Errore(_argomenti_attesi(nome, minimo, massimo))

    def _nome(self, nome):
        if nome in CONSTANTS:
            return
        if nome in self._variabili:
            if nome not in self.letti:
                self.letti.append(nome)
            return
        disponibili = sorted(self._variabili) + sorted(CONSTANTS)
        raise _Errore(f"nome sconosciuto «{nome}»",
                      hint=f"nomi disponibili: {', '.join(disponibili)}")


@dataclass(frozen=True)
class Compiled:
    """Esito di una compilazione: i nomi letti, o il problema."""
    names: Tuple[str, ...] = ()
    problem: Optional[Problem] = None

    @property
    def ok(self) -> bool:
        return self.problem is None


def compile_expression(source: str, variables: Iterable[str] = ()) -> Compiled:
    """Compila come ``compile_expression`` del motore, senza costruire la
    chiusura: dice se il testo e' un'espressione del linguaggio sui nomi
    ``variables`` (piu' le costanti), e quali variabili legge."""
    if not isinstance(source, str):
        return Compiled(problem=Problem("non e' un testo"))
    if not source.strip():
        return Compiled(problem=Problem("e' vuota"))
    try:
        parser = _Parser(_token(source), frozenset(variables))
        parser.tutto()
    except _Errore as errore:
        return Compiled(problem=errore.problem)
    return Compiled(names=tuple(parser.letti))


def outer_parenthesized(source: str) -> bool:
    """True se il testo sta tutto dentro una coppia di parentesi esterne:
    ``(a) + (b)`` comincia e finisce con una parentesi, ma non e' fra
    parentesi (``outer_parenthesized`` del motore)."""
    if not isinstance(source, str):
        return False
    testo = source.strip()
    if len(testo) < 2 or testo[0] != "(" or testo[-1] != ")":
        return False
    aperte = 0
    for posizione, carattere in enumerate(testo):
        if carattere == "(":
            aperte += 1
        elif carattere == ")":
            aperte -= 1
            if aperte == 0:
                return posizione == len(testo) - 1
    return False


def names_in(source: str) -> FrozenSet[str]:
    """I nomi scritti in un testo, alla prima componente (``m1.y`` -> ``m1``):
    la lettura del riparo, senza compilare."""
    return frozenset(n.split(".")[0] for n in _NOMI.findall(source))


def load_time_constant(source: str) -> bool:
    """True se il caricamento la valuta in una costante: tutta fra parentesi,
    e legge solo nomi che la valutazione al caricamento conosce. Vale in ogni
    campo, dentro e fuori da ``EXPRESSION_FIELDS``."""
    if not outer_parenthesized(source) or not names_in(source) <= LOAD_TIME_NAMES:
        return False
    if not _LOAD_TIME_CHARS.fullmatch(source.strip()):
        return False
    # che sia Python valido lo si chiede al parser, senza eseguire niente:
    # ``(0.02 +)`` il caricamento non la valuta, resta una stringa, e la
    # compila (e la rifiuta) l'interprete
    try:
        ast.parse(source.strip(), mode="eval")
    except SyntaxError:
        return False
    return True


#: I caratteri del regex di ``_eval_math_expressions`` (con la virgola, PGE
#: #309).
_LOAD_TIME_CHARS = re.compile(r"[a-zA-Z0-9+\-*/.(), ]+")
