# Recorre el árbol de Lark y llena FunctionDirectory con validaciones de duplicados.

from typing import Optional
from lark import Transformer, Token
from semantics import (
    FunctionDirectory, InvalidTypeError
)

class SemanticBuilder(Transformer):
    """
    Transformer bottom-up:
    - Recolecta listas de (ids, type) en 'decvar' y las eleva vía 'vars_section'.
    - En 'program' añade las globales.
    - En 'func_decl' crea la función, añade parámetros y vars locales.
    """

    # UTILIDADES DE CONVERSIÓN
    def id_list(self, children):
        names = [t.value for t in children if isinstance(t, Token) and t.type == "ID"]
        return names

    def type(self, children):
        tok: Token = children[0]
        if tok.type == "INT":
            return "INT"
        elif tok.type == "FLOAT":
            return "FLOAT"
        raise InvalidTypeError(f"Tipo no soportado en 'type': {tok}")

    # VARS
    def decvar(self, children):
        id_list = children[0]
        vtype = children[2]
        return (id_list, vtype)

    def vars_section(self, children):
        decls = []
        for ch in children:
            if isinstance(ch, tuple) and len(ch) == 2:
                decls.append(ch)
        return decls

    # PARÁMETROS
    def param(self, children):
        name_tok: Token = children[0]
        ptype = children[2]
        return (name_tok.value, ptype)

    def params(self, children):
        pairs = [ch for ch in children if isinstance(ch, tuple) and len(ch) == 2]
        return pairs

    # FUNCIONES
    def func_decl(self, children):
        self._ensure_fd()
        fname = children[1].value
        params_list = children[3]
        local_decls = children[6]

        # Crear función
        fe = self.fd.add_function(fname)

        # Parámetros
        for pname, ptype in (params_list or []):
            self.fd.add_param(fname, pname, ptype)

        # Vars locales
        for names, vtype in (local_decls or []):
            for n in names:
                self.fd.add_local_var(fname, n, vtype)

        return None

    def funcs_section(self, children):
        return None

    # PROGRAMA
    def program(self, children):
        self._ensure_fd()
        global_decls = children[3]

        for names, vtype in (global_decls or []):
            for n in names:
                self.fd.add_global_var(n, vtype)

        return self.fd

    # STATE
    def __init__(self, fd: Optional[FunctionDirectory] = None):
        super().__init__()
        self.fd = fd

    def _ensure_fd(self):
        if self.fd is None:
            self.fd = FunctionDirectory()

# Helper de alto nivel: parsea y construye directorio/tablas
def build_symbols(parse_func, source: str) -> FunctionDirectory:
    """
    parse_func: callable que recibe source y regresa lark.Tree (usa parse() de parse_and_scan)
    """
    tree = parse_func(source)
    builder = SemanticBuilder()
    fd = builder.transform(tree)
    return fd
