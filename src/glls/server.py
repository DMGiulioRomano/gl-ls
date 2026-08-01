"""Il language server: wiring pygls delle feature di gl-ls."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple
from urllib.request import url2pathname

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from . import __version__
from . import actions as actions_mod
from . import completion as completion_mod
from . import diagnostics as diagnostics_mod
from . import hover as hover_mod
from . import inlay as inlay_mod
from . import lens as lens_mod
from . import model as model_mod
from . import navigation as navigation_mod
from . import semtokens as semtokens_mod
from . import symbols as symbols_mod
from . import yamlpos


class GllsServer(LanguageServer):
    """Stato per-documento: parse, modello, diagnostiche, memoria durate."""

    def __init__(self) -> None:
        super().__init__(name="gl-ls", version=__version__)
        self.docs: Dict[str, yamlpos.Document] = {}
        self.models: Dict[str, model_mod.StudyModel] = {}
        self.diags: Dict[str, List[types.Diagnostic]] = {}
        # uri -> {key-path della durata: valore corrente}. La chiave e' il
        # key-path e non una stringa perche' le durate per-stream vivono sotto
        # un nome libero (``streams.<nome>.duration``) che puo' contenere punti:
        # una stringa andrebbe riparsata, e male.
        self.durations: Dict[str, Dict[yamlpos.KeyPath, float]] = {}
        # uri -> {key-path: (vecchio, nuovo)} per la code action di riscala
        self.pending_durations: Dict[
            str, Dict[yamlpos.KeyPath, Tuple[float, float]]] = {}

    # ------------------------------------------------------------------
    def refresh(self, uri: str, text: str, version: Optional[int] = None) -> None:
        doc = yamlpos.parse(text)
        m = model_mod.build(doc)
        self.docs[uri] = doc
        self.models[uri] = m
        self._track_durations(uri, m)
        diags = diagnostics_mod.collect(doc, m)
        self.diags[uri] = diags
        self.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=diags,
                                           version=version)
        )

    def _track_durations(self, uri: str, m: model_mod.StudyModel) -> None:
        """Memoria delle durate per la code action di riscala.

        Si seguono tutte le durate *dichiarate*, non una sola: il default di
        documento (``base.duration``) e quella propria di ogni entry di
        ``streams:``, che dopo granstudies #42 e' la forma dell'override. La
        ``duration:`` top-level non si segue piu': e' una chiave vietata, con
        una diagnostica e due quick fix che la spostano — armarci sopra un
        refactor incoraggerebbe a lasciarla dov'e'."""
        current: Dict[yamlpos.KeyPath, float] = {}
        if m.base_duration is not None:
            current[("base", "duration")] = m.base_duration
        for name, si in m.streams.items():
            if si.duration is not None and si.duration_path is not None:
                current[("streams", name) + tuple(si.duration_path)] = si.duration
        previous = self.durations.get(uri)
        pending = self.pending_durations.setdefault(uri, {})
        if previous is not None:
            for key, new in current.items():
                old = previous.get(key)
                if old is not None and old != new:
                    orig = pending.get(key, (old, new))[0]
                    if orig == new:
                        pending.pop(key, None)  # tornati al valore di partenza
                    else:
                        pending[key] = (orig, new)
        self.durations[uri] = current

    def doc_of(self, uri: str) -> Tuple[yamlpos.Document, model_mod.StudyModel]:
        if uri not in self.docs:
            td = self.workspace.get_text_document(uri)
            self.refresh(uri, td.source)
        return self.docs[uri], self.models[uri]


server = GllsServer()


# ---------------------------------------------------------------------------
# Sync documenti


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: GllsServer, params: types.DidOpenTextDocumentParams) -> None:
    ls.refresh(params.text_document.uri, params.text_document.text,
               params.text_document.version)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: GllsServer, params: types.DidChangeTextDocumentParams) -> None:
    td = ls.workspace.get_text_document(params.text_document.uri)
    ls.refresh(params.text_document.uri, td.source, params.text_document.version)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: GllsServer, params: types.DidCloseTextDocumentParams) -> None:
    uri = params.text_document.uri
    for store in (ls.docs, ls.models, ls.diags, ls.durations,
                  ls.pending_durations):
        store.pop(uri, None)


# ---------------------------------------------------------------------------
# Feature


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=[":", " ", ".", "-"]),
)
def completion(ls: GllsServer, params: types.CompletionParams
               ) -> List[types.CompletionItem]:
    uri = params.text_document.uri
    doc, m = ls.doc_of(uri)
    file_dir = None
    if uri.startswith("file://"):
        file_dir = os.path.dirname(url2pathname(uri[len("file://"):]))
    return completion_mod.complete(doc, m, params.position.line,
                                   params.position.character, file_dir)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls: GllsServer, params: types.HoverParams) -> Optional[types.Hover]:
    doc, m = ls.doc_of(params.text_document.uri)
    return hover_mod.hover(doc, m, params.position.line,
                           params.position.character)


@server.feature(
    types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    types.SemanticTokensLegend(token_types=semtokens_mod.TOKEN_TYPES,
                               token_modifiers=[]),
)
def semantic_tokens(ls: GllsServer, params: types.SemanticTokensParams
                    ) -> types.SemanticTokens:
    doc, m = ls.doc_of(params.text_document.uri)
    return types.SemanticTokens(data=semtokens_mod.tokens(doc, m))


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: GllsServer, params: types.DocumentSymbolParams
                    ) -> List[types.DocumentSymbol]:
    doc, m = ls.doc_of(params.text_document.uri)
    return symbols_mod.symbols(doc, m)


@server.feature(types.TEXT_DOCUMENT_INLAY_HINT)
def inlay_hint(ls: GllsServer, params: types.InlayHintParams
               ) -> List[types.InlayHint]:
    doc, m = ls.doc_of(params.text_document.uri)
    return inlay_mod.hints(doc, m, params.range.start.line,
                           params.range.end.line)


@server.feature(types.TEXT_DOCUMENT_CODE_LENS)
def code_lens(ls: GllsServer, params: types.CodeLensParams
              ) -> List[types.CodeLens]:
    doc, m = ls.doc_of(params.text_document.uri)
    return lens_mod.lenses(doc, m)


@server.feature(
    types.TEXT_DOCUMENT_CODE_ACTION,
    types.CodeActionOptions(code_action_kinds=[
        types.CodeActionKind.QuickFix,
        types.CodeActionKind.RefactorRewrite,
    ]),
)
def code_action(ls: GllsServer, params: types.CodeActionParams
                ) -> List[types.CodeAction]:
    uri = params.text_document.uri
    doc, m = ls.doc_of(uri)
    diags = [d for d in ls.diags.get(uri, [])
             if _ranges_touch(d.range, params.range)]
    pending = ls.pending_durations.get(uri, {})
    return actions_mod.collect(doc, m, uri, params.range, diags, pending)


def _ranges_touch(a: types.Range, b: types.Range) -> bool:
    return not (a.end.line < b.start.line or a.start.line > b.end.line)


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(ls: GllsServer, params: types.DefinitionParams
               ) -> Optional[types.Location]:
    doc, m = ls.doc_of(params.text_document.uri)
    return navigation_mod.definition(doc, m, params.text_document.uri,
                                     params.position.line,
                                     params.position.character)


@server.feature(types.TEXT_DOCUMENT_REFERENCES)
def references(ls: GllsServer, params: types.ReferenceParams
               ) -> List[types.Location]:
    doc, m = ls.doc_of(params.text_document.uri)
    return navigation_mod.references(
        doc, m, params.text_document.uri,
        params.position.line, params.position.character,
        params.context.include_declaration if params.context else True,
    )


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_LINK)
def document_link(ls: GllsServer, params: types.DocumentLinkParams
                  ) -> List[types.DocumentLink]:
    doc, m = ls.doc_of(params.text_document.uri)
    return navigation_mod.document_links(doc, m, params.text_document.uri)


@server.command("glls.noop")
def noop(ls: GllsServer, *args) -> None:
    """Comando vuoto per i code lens informativi."""
    return None
