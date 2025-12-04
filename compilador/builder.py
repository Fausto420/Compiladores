from typing import Optional, List, Tuple
from lark import Transformer, Token, Tree
from semantics import (
    FunctionDirectory,
    TypeName,
    INT,
    FLOAT,
    VOID,
    InvalidTypeError,
    SemanticError,
)


# Helper functions for tree traversal
def find_child_tree(children: list, data_name: str) -> Optional[Tree]:
    """
    Encuentra el primer hijo Tree con el data attribute especificado.
    """
    for child in children:
        if isinstance(child, Tree) and child.data == data_name:
            return child
    return None


def find_token(children: list, token_type: str) -> Optional[Token]:
    """
    Encuentra el primer Token con el tipo especificado.
    """
    for child in children:
        if isinstance(child, Token) and child.type == token_type:
            return child
    return None


def find_all_trees(children: list, data_name: str) -> List[Tree]:
    """
    Encuentra todos los hijos Tree con el data attribute especificado.
    """
    return [child for child in children if isinstance(child, Tree) and child.data == data_name]

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
    def lista_ids(self, children):
        """
        Transforma la lista de IDs en una lista de strings con
        los nombres de las variables.
        """
        return [
            token.value
            for token in children
            if isinstance(token, Token) and token.type == "ID"
        ]

    def tipo(self, children):
        """
        Recibe un token de tipo y lo traduce al TypeName usado en semantics.py.
        """
        type_token: Token = children[0]

        if type_token.type == "ENTERO":
            return INT
        elif type_token.type == "FLOTANTE":
            return FLOAT

        raise InvalidTypeError(f"Tipo no soportado en la regla 'tipo': {type_token}")
    
    def tipo_retorno(self, children):
        """
        Convierte la regla 'tipo_retorno' de la gramática en un TypeName.
        """
        child = children[0]

        # Caso: token NULA directamente
        if isinstance(child, Token) and child.type == "NULA":
            return VOID

        # Caso: ya es un TypeName (INT o FLOAT) que vino de la regla 'tipo'
        if isinstance(child, str) and child in (INT, FLOAT):
            return child

        # Cualquier otra cosa es un error de consistencia
        raise SemanticError(
            f"Valor inesperado en tipo_retorno: {child!r}"
        )

    def declaracion_var(self, children):
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

    def vars_seccion(self, children):
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
        - Guardar su tipo de retorno (void, int o float).
        - Agregar sus parámetros.
        - Agregar sus variables locales.
        """
        function_name: Optional[str] = None
        function_return_type: TypeName = VOID
        parameter_declarations: List[Tuple[str, TypeName]] = []
        local_declarations: List[Tuple[List[str], TypeName]] = []

        # 1. Recorre los hijos y extrae lo que interesa
        for element in children:
            # Primero viene el tipo de retorno (regla func_return_type)
            if (
                isinstance(element, str)
                and element in (INT, FLOAT, VOID)
                and function_return_type == VOID  # solo toma el primero
            ):
                function_return_type = element

            # Luego viene el nombre de la función
            elif isinstance(element, Token) and element.type == "ID" and function_name is None:
                function_name = element.value

            # Listas: pueden ser parámetros o declaraciones locales
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

        # 2. Crea la función en el directorio, con su tipo de retorno
        self.function_directory.add_function(
            function_name=function_name,
            return_type=function_return_type,
        )

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
    def programa(self, children):
        """
        Punto neurálgico:
        - Tomar las declaraciones de 'vars_seccion' y agregarlas a la tabla de variables globales del FunctionDirectory.
        - Las funciones ya se procesan en func_decl.
        - Al final, regresar el FunctionDirectory construido.
        """
        # Extraer las declaraciones globales de variables
        global_declarations: List[Tuple[List[str], TypeName]] = []
        for element in children:
            # 'vars_seccion' produce una lista de ([nombres], tipo)
            if isinstance(element, list) and element:
                first_item = element[0]
                # Identifica la estructura de vars_seccion: lista de tuplas ([nombres], tipo)
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

    # Regla de inicio
    def start(self, children):
        """
        start: programa
        Simplemente regresa el resultado de programa.
        """
        return children[0]

# Función de ayuda para construir las tablas
def build_symbol_tables(parse_function, source_code: str) -> FunctionDirectory:
    parse_tree = parse_function(source_code) # 1. Parsea el código
    builder = SemanticBuilder() # 2. Crea el builder
    function_directory = builder.transform(parse_tree) # 3. Construye las tablas
    return function_directory
