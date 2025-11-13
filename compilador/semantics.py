from typing import Dict, List, Optional
from dataclasses import dataclass, field

TypeName = str

INT: TypeName = "INT"
FLOAT: TypeName = "FLOAT"
BOOL: TypeName = "BOOL"
VOID: TypeName = "VOID"

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
OPERATOR_ALIASES: Dict[str, str] = {
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
    # Operadores aritméticos
    "PLUS": {
        (INT, INT): INT,
        (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT,
        (FLOAT, FLOAT): FLOAT,
    },
    "MINUS": {
        (INT, INT): INT,
        (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT,
        (FLOAT, FLOAT): FLOAT,
    },
    "STAR": {
        (INT, INT): INT,
        (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT,
        (FLOAT, FLOAT): FLOAT,
    },
    "SLASH": {
        (INT, INT): FLOAT,
        (INT, FLOAT): FLOAT,
        (FLOAT, INT): FLOAT,
        (FLOAT, FLOAT): FLOAT,
    },

    # Operadores relacionales
    "GREATER": {
        (INT, INT): BOOL,
        (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL,
        (FLOAT, FLOAT): BOOL,
    },
    "LESS": {
        (INT, INT): BOOL,
        (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL,
        (FLOAT, FLOAT): BOOL,
    },
    "NOTEQUAL": {
        (INT, INT): BOOL,
        (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL,
        (FLOAT, FLOAT): BOOL,
    },
    "EQUAL": {
        (INT, INT): BOOL,
        (INT, FLOAT): BOOL,
        (FLOAT, INT): BOOL,
        (FLOAT, FLOAT): BOOL,
    },
}

def _normalize_operator(operator: str) -> str:
    """
    Recibe un operador, como "+" o "PLUS",
    y regresa siempre el nombre normalizado, por ejemplo "PLUS".
    """
    return OPERATOR_ALIASES.get(operator, operator)

def result_type(operator: str, left_type: TypeName, right_type: TypeName) -> TypeName:
    """
    Devuelve el tipo que resulta de 'left_type (operator) right_type'
    según el cubo semántico.

    Lanza InvalidTypeError si:
    - el operador no está en el cubo, o
    - la combinación de tipos no es válida.
    """
    normalized_operator = _normalize_operator(operator)
    operator_table = SEMANTIC_CUBE.get(normalized_operator)

    if operator_table is None:
        raise InvalidTypeError(f"Operador no soportado en el cubo semántico: {operator}")

    # Busca la tupla (tipo_izq, tipo_der) en la tabla del operador
    try:
        return operator_table[(left_type, right_type)]
    except KeyError as error:
        raise InvalidTypeError(
            f"Tipos incompatibles para {operator}: {left_type} {operator} {right_type}"
        ) from error
    
def assert_assign(left_type: TypeName, right_type: TypeName, context: str = "assignment") -> None:
    if left_type == INT:
        if right_type == INT:
            return
        raise InvalidTypeError(f"Tipos incompatibles en {context}: INT = {right_type}")

    if left_type == FLOAT:
        if right_type in (INT, FLOAT):
            return
        raise InvalidTypeError(f"Tipos incomopatibles en {context}: FLOAT = {right_type}")

    raise InvalidTypeError(f"Tipo de Left-hand side no asignable: {left_type}")

def ensure_bool(expression_type: TypeName, context: str = "condition") -> None:
    if expression_type != BOOL:
        raise InvalidTypeError(f"Expected BOOL in {context}, got {expression_type}")

# TABLA DE VARIABLES
@dataclass
class VariableInfo:
    """
    Representa una variable dentro de una tabla de variables.

    Atributos:
        name: nombre de la variable (por ejemplo, "x").
        var_type: tipo de la variable (INT o FLOAT).
        is_parameter: True si la variable es un parámetro de función.
        parameter_position: posición del parámetro en la lista de parámetros (0, 1, 2, ...). None si no es parámetro.
    """
    name: str
    var_type: TypeName
    is_parameter: bool = False
    parameter_position: Optional[int] = None

@dataclass
class VariableTable:
    """
    Tabla de variables para un scope (global o local).

    Internamente usa un diccionario: nombre_variable -> VariableInfo
    """
    variables: Dict[str, VariableInfo] = field(default_factory=dict)

    def add_variable(
        self,
        variable_name: str,
        variable_type: TypeName,
        is_parameter: bool = False,
        parameter_position: Optional[int] = None,
    ) -> None:
        # Valida que no haya duplicados en el mismo scope
        if variable_name in self.variables:
            raise DuplicateVariableError(
                f"Variable '{variable_name}' ya fue declarada en este scope."
            )

        if variable_type not in (INT, FLOAT):
            raise InvalidTypeError(
                f"Tipo de variable no soportado: {variable_type}"
            )

        # Crea el objeto VariableInfo y lo guardam en el diccionario
        self.variables[variable_name] = VariableInfo(
            name=variable_name,
            var_type=variable_type,
            is_parameter=is_parameter,
            parameter_position=parameter_position,
        )

    def get_variable(self, variable_name: str) -> VariableInfo:
        try:
            return self.variables[variable_name]
        except KeyError as error:
            raise UnknownVariableError(
                f"Variable '{variable_name}' no encontrada en este scope."
            ) from error

    def contains_variable(self, variable_name: str) -> bool:
        return variable_name in self.variables

    def to_dict(self) -> Dict[str, dict]:
        result: Dict[str, dict] = {}
        for name, info in self.variables.items():
            result[name] = {
                "type": info.var_type,
                "is_parameter": info.is_parameter,
                "parameter_position": info.parameter_position,
            }
        return result

# DIRECTORIO DE FUNCIONES
@dataclass
class FunctionInfo:
    """
    Representa una función del programa.

    Atributos:
        name: nombre de la función.
        return_type: tipo de retorno (default con VOID).
        parameter_list: lista de parámetros en orden.
        local_variables: tabla de variables locales a la función (incluye también a los parámetros).
    """
    name: str
    return_type: TypeName = VOID
    parameter_list: List[VariableInfo] = field(default_factory=list)
    local_variables: VariableTable = field(default_factory=VariableTable)

    def add_parameter(self, parameter_name: str, parameter_type: TypeName) -> None:
        for existing_parameter in self.parameter_list:
            if existing_parameter.name == parameter_name:
                raise DuplicateParameterError(
                    f"Parámetro '{parameter_name}' ya fue declarado en la función '{self.name}'."
                )

        parameter_position = len(self.parameter_list)

        parameter_info = VariableInfo(
            name=parameter_name,
            var_type=parameter_type,
            is_parameter=True,
            parameter_position=parameter_position,
        )

        self.parameter_list.append(parameter_info)

        self.local_variables.add_variable(
            variable_name=parameter_name,
            variable_type=parameter_type,
            is_parameter=True,
            parameter_position=parameter_position,
        )

    def add_local_variable(self, variable_name: str, variable_type: TypeName) -> None:
        self.local_variables.add_variable(
            variable_name=variable_name,
            variable_type=variable_type,
            is_parameter=False,
            parameter_position=None,
        )

@dataclass
class FunctionDirectory:
    """
    Directorio de funciones de todo el programa Patito.

    Atributos:
        global_variables: tabla de variables globales.
        functions: diccionario nombre_función -> FunctionInfo.
    """
    global_variables: VariableTable = field(default_factory=VariableTable)
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)

    # Funciones para declarar y obtener funciones
    def add_function(self, function_name: str, return_type: TypeName = VOID) -> FunctionInfo:
        if function_name in self.functions:
            raise DuplicateFunctionError(
                f"Función '{function_name}' ya fue declarada."
            )

        if return_type != VOID:
            raise InvalidTypeError(
                f"Por ahora solo se permiten funciones VOID. Intento de usar tipo: {return_type}"
            )

        function_info = FunctionInfo(name=function_name, return_type=return_type)
        self.functions[function_name] = function_info
        return function_info

    def get_function(self, function_name: str) -> FunctionInfo:
        try:
            return self.functions[function_name]
        except KeyError as error:
            raise UnknownFunctionError(
                f"Función '{function_name}' no ha sido declarada."
            ) from error

    # Funciones de ayuda para agregar params/vars
    def add_parameter_to_function(
        self,
        function_name: str,
        parameter_name: str,
        parameter_type: TypeName,
    ) -> None:
        function_info = self.get_function(function_name)
        function_info.add_parameter(parameter_name, parameter_type)

    def add_local_variable_to_function(
        self,
        function_name: str,
        variable_name: str,
        variable_type: TypeName,
    ) -> None:
        function_info = self.get_function(function_name)
        function_info.add_local_variable(variable_name, variable_type)

    def add_global_variable(self, variable_name: str, variable_type: TypeName) -> None:
        self.global_variables.add_variable(variable_name, variable_type)

    # Búsqueda de variables respetando el scope
    def lookup_variable(
        self,
        variable_name: str,
        current_function_name: Optional[str] = None,
    ) -> VariableInfo:
        """
        Busca una variable por nombre, respetando las reglas de scope:

        1. Si se indica current_function_name, se busca primero en las variables locales de esa función.
        2. Si no se encuentra ahí, se busca en las variables globales.
        3. Si no se encuentra en ningún lado, lanza UnknownVariableError.
        """
        if current_function_name is not None:
            function_info = self.get_function(current_function_name)
            if function_info.local_variables.contains_variable(variable_name):
                return function_info.local_variables.get_variable(variable_name)

        if self.global_variables.contains_variable(variable_name):
            return self.global_variables.get_variable(variable_name)

        raise UnknownVariableError(
            f"Variable '{variable_name}' no existe ni en la función '{current_function_name}' "f"ni en el scope global."
        )

    def to_dict(self) -> dict:
        result = {
            "globals": self.global_variables.to_dict(),
            "functions": {},
        }

        for func_name, func_info in self.functions.items():
            result["functions"][func_name] = {
                "return_type": func_info.return_type,
                "parameters": [
                    {
                        "name": param.name,
                        "type": param.var_type,
                        "position": param.parameter_position,
                    }
                    for param in func_info.parameter_list
                ],
                "locals": func_info.local_variables.to_dict(),
            }
        
        return result