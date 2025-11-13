from typing import Optional, List, Tuple
from lark import Transformer, Token

from semantics import (
    FunctionDirectory,
    TypeName,
    INT,
    FLOAT,
    InvalidTypeError,
    SemanticError,
)

class SemanticBuilder(Transformer):
    """
    Recorre el árbol sintáctico generado por Lark y construye:

    - El directorio de funciones del programa (FunctionDirectory).
    - La tabla de variables globales.
    - Las tablas de variables locales para cada función.

    Este builder se encarga solo de las declaraciones:
    - Declaración del programa (program).
    - Declaraciones de variables (vars_section, decvar).
    - Declaraciones de funciones (func_decl) y parámetros (params).
    """

    def __init__(self, function_directory: Optional[FunctionDirectory] = None):
        super().__init__()

        # Si se pasa un directorio existente, se usa;
        # si no, crea uno nuevo vacío.
        self.function_directory: FunctionDirectory = (
            function_directory if function_directory is not None else FunctionDirectory()
        )

    # 1) Reglas auxiliares de conversión
    def id_list(self, children):
        """
        Transforma la lista de IDs en una lista de strings con
        los nombres de las variables.
        """
        identifier_names: List[str] = []

        for element in children:
            if isinstance(element, Token) and element.type == "ID":
                identifier_names.append(element.value)

        return identifier_names

    def type(self, children):
        """
        Recibe un token de tipo y lo traduce al TypeName usado en semantics.py.
        """
        type_token: Token = children[0]

        if type_token.type == "INT":
            return INT
        elif type_token.type == "FLOAT":
            return FLOAT

        raise InvalidTypeError(f"Tipo no soportado en la regla 'type': {type_token}")

    def decvar(self, children):
        """
        Transforma en una tupla: (lista_de_nombres, tipo_de_variable)
        """
        identifier_list: List[str] = []
        variable_type: TypeName = "VOID"

        for element in children:
            if isinstance(element, list):
                identifier_list = element
            elif isinstance(element, str) and element in (INT, FLOAT):
                variable_type = element

        return (identifier_list, variable_type)

    def vars_section(self, children):
        """
        Se quiere regresar una lista de tuplas:
            [
                ([nombres_1], tipo_1),
                ([nombres_2], tipo_2),
                ...
            ]
        donde cada tupla representa una declaración de variables.
        """
        declarations: List[Tuple[List[str], TypeName]] = []

        for element in children:
            if isinstance(element, tuple) and len(element) == 2:
                declarations.append(element)

        return declarations

    def param(self, children):
        """
        Transforma en una tupla: (nombre_parametro, tipo_parametro)
        """
        parameter_name: str = ""
        parameter_type: TypeName = "VOID"

        for element in children:
            if isinstance(element, Token) and element.type == "ID":
                parameter_name = element.value
            elif isinstance(element, str) and element in (INT, FLOAT):
                parameter_type = element

        return (parameter_name, parameter_type)

    def params(self, children):
        """
        Regresa una lista de pares: [(nombre1, tipo1), (nombre2, tipo2), ...]
        """
        parameter_declarations: List[Tuple[str, TypeName]] = []

        for element in children:
            if isinstance(element, tuple) and len(element) == 2:
                parameter_declarations.append(element)

        return parameter_declarations

    # 2) Puntos neurálgicos: funciones
    def func_decl(self, children):
        """
        Punto neurálgico:
        - Crear la entrada de la función en el FunctionDirectory.
        - Agregar sus parámetros.
        - Agregar sus variables locales.
        """
        function_name: Optional[str] = None
        parameter_declarations: List[Tuple[str, TypeName]] = []
        local_declarations: List[Tuple[List[str], TypeName]] = []

        # 1. Recorre los hijos y extrae lo que interesan
        for element in children:
            if isinstance(element, Token) and element.type == "ID" and function_name is None:
                function_name = element.value

            # 'params' produce una lista de (nombre, tipo)
            elif isinstance(element, list) and element:
                first_item = element[0]

                # Caso: lista de parámetros -> (nombre, tipo)
                if isinstance(first_item, tuple) and isinstance(first_item[0], str):
                    parameter_declarations = element

                # Caso: lista de declaraciones locales -> ([nombres], tipo)
                elif isinstance(first_item, tuple) and isinstance(first_item[0], list):
                    local_declarations = element

        if function_name is None:
            raise SemanticError("No se encontró el nombre de la función en func_decl.")

        # 2. Crea la función en el directorio
        self.function_directory.add_function(function_name)

        # 3. Agrega los parámetros a la función
        for parameter_name, parameter_type in parameter_declarations:
            self.function_directory.add_parameter_to_function(
                function_name=function_name,
                parameter_name=parameter_name,
                parameter_type=parameter_type,
            )

        # 4. Agrega las variables locales (que NO son parámetros)
        for identifier_list, variable_type in local_declarations:
            for variable_name in identifier_list:
                self.function_directory.add_local_variable_to_function(
                    function_name=function_name,
                    variable_name=variable_name,
                    variable_type=variable_type,
                )

        return None

    # 3) Punto neurálgico: programa principal
    def program(self, children):
        """
        Punto neurálgico:
        - Tomar las declaraciones de 'vars_section' y agregarlas a la tabla de variables globales del FunctionDirectory.
        - Las funciones ya se procesan en func_decl.
        - Al final, regresar el FunctionDirectory construido.
        """
        program_name: Optional[str] = None
        global_declarations: List[Tuple[List[str], TypeName]] = []

        for element in children:
            if isinstance(element, Token) and element.type == "ID" and program_name is None:
                program_name = element.value

            # 'vars_section' produce una lista de ([nombres], tipo).
            elif isinstance(element, list) and element:
                first_item = element[0]
                # Identifica la estructura de vars_section:
                # lista de tuplas ([nombres], tipo)
                if isinstance(first_item, tuple) and isinstance(first_item[0], list):
                    global_declarations = element

        # Agregar variables globales al directorio
        for identifier_list, variable_type in global_declarations:
            for variable_name in identifier_list:
                self.function_directory.add_global_variable(
                    variable_name=variable_name,
                    variable_type=variable_type,
                )
        
        return self.function_directory

# Función de ayuda para construir las tablas
def build_symbol_tables(parse_function, source_code: str) -> FunctionDirectory:
    parse_tree = parse_function(source_code) # 1. Parsea el código
    builder = SemanticBuilder() # 2. Crea el builder
    function_directory = builder.transform(parse_tree) # 3. Construye las tablas
    return function_directory
