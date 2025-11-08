from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal

# TIPOS BÁSICOS
TypeName = Literal["INT", "FLOAT", "BOOL", "VOID"]

INT, FLOAT, BOOL, VOID = "INT", "FLOAT", "BOOL", "VOID"

# ERRORES SEMÁNTICOS
class SemanticError(Exception):
    pass

class DuplicateFunctionError(SemanticError):
    pass

class DuplicateVariableError(SemanticError):
    pass

class DuplicateParameterError(SemanticError):
    pass

class UnknownFunctionError(SemanticError):
    pass

class UnknownVariableError(SemanticError):
    pass

class InvalidTypeError(SemanticError):
    pass

# CUBO SEMÁNTICO
OP_ALIASES = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    ">": "GREATER",
    "<": "LESS",
    "!=": "NOTEQUAL",
    "==": "EQUAL",
}

SEMANTIC_CUBE: Dict[str, Dict[tuple, TypeName]] = {
    "PLUS": {
        (INT, INT): INT, (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT, (FLOAT, FLOAT): FLOAT,
    },
    "MINUS": {
        (INT, INT): INT, (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT, (FLOAT, FLOAT): FLOAT,
    },
    "STAR": {
        (INT, INT): INT, (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT, (FLOAT, FLOAT): FLOAT,
    },
    "SLASH": {
        (INT, INT): FLOAT, (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT, (FLOAT, FLOAT): FLOAT,
    },
    "GREATER": {
        (INT, INT): BOOL, (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL, (FLOAT, FLOAT): BOOL,
    },
    "LESS": {
        (INT, INT): BOOL, (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL, (FLOAT, FLOAT): BOOL,
    },
    "NOTEQUAL": {
        (INT, INT): BOOL, (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL, (FLOAT, FLOAT): BOOL,
    },
    "EQUAL": {
        (INT, INT): BOOL, (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL, (FLOAT, FLOAT): BOOL,
    },
}

def _opkey(op: str) -> str:
    """Normaliza el nombre del operador: acepta 'PLUS' o '+' y regresa 'PLUS'."""
    return OP_ALIASES.get(op, op)

def result_type(op: str, left: TypeName, right: TypeName) -> TypeName:
    """
    Devuelve el tipo que resulta de 'left (op) right' según el cubo.
    Si la combinación no es válida, se lanza InvalidTypeError.
    """
    key = _opkey(op)
    table = SEMANTIC_CUBE.get(key)
    if not table:
        raise InvalidTypeError(f"Operador no soportado en el cubo: {op}")
    try:
        return table[(left, right)]
    except KeyError as e:
        raise InvalidTypeError(
            f"Tipos incompatibles para {op}: {left} {op} {right}"
        ) from e

def assert_assign(lhs: TypeName, rhs: TypeName, ctx: str = "assignment") -> None:
    """
    Valida 'lhs = rhs' según las reglas:
      - INT <- INT   (ok)
      - FLOAT <- INT   (promoción)
      - FLOAT <- FLOAT (ok)
      - INT <- FLOAT (error)
      - (INT/FLOAT) <- BOOL (error)
    Lanza InvalidTypeError si no es válido.
    """
    if lhs == INT:
        if rhs == INT:
            return
        raise InvalidTypeError(f"Incompatible types in {ctx}: INT = {rhs}")
    if lhs == FLOAT:
        if rhs in (INT, FLOAT):
            return
        raise InvalidTypeError(f"Incompatible types in {ctx}: FLOAT = {rhs}")
    raise InvalidTypeError(f"Left-hand side type not assignable: {lhs}")

def ensure_bool(t: TypeName, ctx: str = "condition") -> None:
    """Exige que 't' sea BOOL (para if/while)."""
    if t != BOOL:
        raise InvalidTypeError(f"Expected BOOL in {ctx}, got {t}")

# TABLAS DE VARIABLES
@dataclass
class VarEntry:
    name: str
    vtype: TypeName
    is_param: bool = False
    param_pos: Optional[int] = None

@dataclass
class VariableTable:
    """Tabla de variables por scope"""
    _vars: Dict[str, VarEntry] = field(default_factory=dict)

    def add(self, name: str, vtype: TypeName, *, is_param: bool = False, param_pos: Optional[int] = None) -> VarEntry:
        if name in self._vars:
            raise DuplicateVariableError(f"Variable '{name}' redeclarada en el mismo scope.")
        if vtype not in (INT, FLOAT):
            raise InvalidTypeError(f"Tipo inválido para variable '{name}': {vtype}")
        entry = VarEntry(name=name, vtype=vtype, is_param=is_param, param_pos=param_pos)
        self._vars[name] = entry
        return entry

    def get(self, name: str) -> VarEntry:
        try:
            return self._vars[name]
        except KeyError as e:
            raise UnknownVariableError(f"Variable '{name}' no declarada en este scope.") from e

    def exists(self, name: str) -> bool:
        return name in self._vars

    def to_dict(self):
        return {k: vars(v) for k, v in self._vars.items()}

# DIRECTORIO DE FUNCIONES
@dataclass
class Param:
    name: str
    ptype: TypeName

@dataclass
class FunctionEntry:
    name: str
    rtype: TypeName = VOID
    params: List[Param] = field(default_factory=list)
    vartable: VariableTable = field(default_factory=VariableTable)

    def add_param(self, name: str, ptype: TypeName):
        if ptype not in (INT, FLOAT):
            raise InvalidTypeError(f"Tipo de parámetro inválido en función '{self.name}': {ptype}")
        if any(p.name == name for p in self.params):
            raise DuplicateParameterError(f"Parámetro '{name}' duplicado en función '{self.name}'.")
        pos = len(self.params)
        self.params.append(Param(name=name, ptype=ptype))
        if self.vartable.exists(name):
            raise DuplicateVariableError(f"Identificador '{name}' ya existe en función '{self.name}'.")
        self.vartable.add(name, ptype, is_param=True, param_pos=pos)

    def add_local(self, name: str, vtype: TypeName):
        if self.vartable.exists(name):
            raise DuplicateVariableError(f"Variable '{name}' duplicada en función '{self.name}'.")
        self.vartable.add(name, vtype)

@dataclass
class FunctionDirectory:
    """Directorio de funciones del programa"""
    globals: VariableTable = field(default_factory=VariableTable)
    funcs: Dict[str, FunctionEntry] = field(default_factory=dict)

    # Funciones
    def add_function(self, name: str, rtype: TypeName = VOID) -> FunctionEntry:
        if name in self.funcs:
            raise DuplicateFunctionError(f"Función '{name}' ya declarada.")
        if rtype != VOID:
            raise InvalidTypeError("En esta versión de Patito, las funciones son solo VOID.")
        entry = FunctionEntry(name=name, rtype=rtype)
        self.funcs[name] = entry
        return entry

    def get_function(self, name: str) -> FunctionEntry:
        try:
            return self.funcs[name]
        except KeyError as e:
            raise UnknownFunctionError(f"Función '{name}' no declarada.") from e

    def add_param(self, func: str, name: str, ptype: TypeName):
        self.get_function(func).add_param(name, ptype)

    def add_local_var(self, func: str, name: str, vtype: TypeName):
        self.get_function(func).add_local(name, vtype)

    # Variables globales
    def add_global_var(self, name: str, vtype: TypeName):
        self.globals.add(name, vtype)

    # Búsqueda con cadena de scopes
    def lookup(self, name: str, current_func: Optional[str]) -> VarEntry:
        if current_func:
            fe = self.get_function(current_func)
            if fe.vartable.exists(name):
                return fe.vartable.get(name)
        if self.globals.exists(name):
            return self.globals.get(name)
        raise UnknownVariableError(f"Identificador '{name}' no está declarado en el scope visible.")

    # Serialización simple para depurar
    def to_dict(self):
        return {
            "globals": self.globals.to_dict(),
            "funcs": {
                fname: {
                    "rtype": f.rtype,
                    "params": [vars(p) for p in f.params],
                    "vars": f.vartable.to_dict(),
                } for fname, f in self.funcs.items()
            }
        }
