from dataclasses import dataclass
from typing import Optional, List, Dict
from lark import Tree, Token
from semantics import (
    FunctionDirectory,
    TypeName,
    INT,
    FLOAT,
    BOOL,
    VOID,
    result_type,
    assert_assign,
    assert_return,
    ensure_bool,
    SemanticError,
)
from intermediate_code_structures import (
    IntermediateCodeContext,
    Quadruple,
)
from virtual_memory import VirtualMemory


# Resultado de subexpresiones
@dataclass
class ExpressionResult:
    """
    Representa el resultado de evaluar una subexpresión.
    address: dirección virtual donde se encuentra el valor (variable, constante o temporal).
    result_type: Tipo del valor (INT, FLOAT, BOOL).
    """
    address: int
    result_type: TypeName

# Generador principal de cuádruplos
class ExpressionQuadrupleGenerator:
    """
    Recorre el árbol sintáctico de Lark y llena un IntermediateCodeContext
    con cuádruplos para expresiones aritméticas y relacionales; y
    estatutos lineales: assign, print_stmt, fcall; y estatutos no lineales: 
    condition (if/else), cycle (while).
    """

    def __init__(
        self, 
        function_directory: FunctionDirectory, 
        context: Optional[IntermediateCodeContext] = None, 
        virtual_memory: Optional[VirtualMemory] = None
    ) -> None:
        # Directorio de funciones y variables (builder.py)
        self.function_directory: FunctionDirectory = function_directory

        # Contexto con pilas, temporales y fila de cuádruplos
        self.context: IntermediateCodeContext = (
            context if context is not None else IntermediateCodeContext()
        )

        # Memoria virtual: aquí se asignan direcciones a temporales y constantes
        self.virtual_memory: VirtualMemory = (
            virtual_memory if virtual_memory is not None else VirtualMemory()
        )

        # Nombre de la función actual (None = cuerpo principal)
        self.current_function_name: Optional[str] = None

        # Indice del primer cuádruplo ejecutable de cada función (después de BEGINFUNC).
        # Se usa para rellenar el destino de los GOSUB.
        self.function_start_indices: Dict[str, int] = {}

        # GOTO pendientes generados por 'return;' o 'return expr;'.
        # Al finalizar la función se cubren para que apunten al ENDFUNC.
        self.pending_return_gotos: Dict[str, List[int]] = {}

        # GOSUB pendientes de saber a qué índice de cuádruplo deben saltar
        self.pending_gosub_fixups: Dict[str, List[int]] = {}

    def _emit_binary_operation(
        self,
        operator_name: str,
        left: "ExpressionResult",
        right: "ExpressionResult",
    ) -> "ExpressionResult":
        """
        Genera el cuádruplo para una operación binaria (aritmética o relacional),
        usando las pilas del contexto y regresando el resultado como un nuevo
        ExpressionResult basado en direcciones virtuales.
        """

        # 1) Meter operandos + tipos en las pilas (direcciones virtuales)
        self.context.push_operand(left.address, left.result_type)
        self.context.push_operand(right.address, right.result_type)
        self.context.push_operator(operator_name)

        # 2) Sacar de las pilas para generar el cuádruplo
        op = self.context.operator_stack.pop()
        right_address = self.context.operand_stack.pop()
        right_type = self.context.type_stack.pop()
        left_address = self.context.operand_stack.pop()
        left_type = self.context.type_stack.pop()

        # 3) Determinar tipo resultante usando el cubo semántico
        result_t = result_type(op, left_type, right_type)

        # 4) Pedir una dirección virtual para el temporal resultante
        temp_address = self.virtual_memory.allocate_temporary(result_t)

        # 5) Generar el cuádruplo con direcciones virtuales
        self.context.quadruples.enqueue(
            Quadruple(op, left_address, right_address, temp_address)
        )

        # 6) Meter de nuevo el resultado a las pilas
        self.context.push_operand(temp_address, result_t)

        # 7) Regresar un objeto ExpressionResult con la dirección
        return ExpressionResult(temp_address, result_t)

    # Entradas de alto nivel
    def generate_program(self, program_tree: Tree) -> IntermediateCodeContext:
        """
        Entra al nodo 'start' o 'programa' y genera cuádruplos para todas las funciones de funcs_seccion y
        el cuerpo principal (después de INICIO).
        """
        # Si es el nodo start, extrae el programa
        if isinstance(program_tree, Tree) and program_tree.data == "start":
            program_tree = program_tree.children[0]

        if not isinstance(program_tree, Tree) or program_tree.data != "programa":
            raise ValueError("generate_program espera un Tree('start') o Tree('programa').")

        # 1) Funciones
        for child in program_tree.children:
            if isinstance(child, Tree) and child.data == "funcs_seccion":
                self._generate_funcs_seccion(child)

        # 2) Cuerpo principal (INICIO estatutos FIN)
        for child in program_tree.children:
            if isinstance(child, Tree) and child.data == "cuerpo_principal":
                self.current_function_name = None
                self._generate_cuerpo_principal(child)

        return self.context

    def _generate_funcs_seccion(self, funcs_seccion_tree: Tree) -> None:
        """funcs_seccion: func_decl*"""
        for child in funcs_seccion_tree.children:
            if isinstance(child, Tree) and child.data == "func_decl":
                self._generate_function(child)

    def _generate_function(self, func_decl_tree: Tree) -> None:
        """
        func_decl: tipo_retorno ID PAREN_IZQ params? PAREN_DER LLAVE_IZQ vars_seccion? estatutos LLAVE_DER PUNTO_COMA
        """
        function_name: Optional[str] = None
        estatutos_tree: Optional[Tree] = None

        # Busca el nombre (ID)
        for child in func_decl_tree.children:
            if isinstance(child, Token) and child.type == "ID":
                function_name = child.value
                break

        if function_name is None:
            raise ValueError("func_decl sin ID de función.")

        # Busca el nodo estatutos
        for child in func_decl_tree.children:
            if isinstance(child, Tree) and child.data == "estatutos":
                estatutos_tree = child
                break

        if estatutos_tree is None:
            raise ValueError(f"func_decl de '{function_name}' sin estatutos.")

        previous_function_name = self.current_function_name
        self.current_function_name = function_name

        # Crea o reinicia la lista de GOTO generados por 'return' para esta función.
        self.pending_return_gotos[function_name] = []

        # Marca inicio de función (BEGINFUNC) y registra el índice de inicio real del cuerpo
        begin_index = self.context.quadruples.enqueue(
            Quadruple("BEGINFUNC", function_name, None, None)
        )
        # El primer cuádruplo ejecutable del cuerpo es el siguiente a BEGINFUNC
        self.function_start_indices[function_name] = begin_index + 1

        # Si ya había GOSUB pendientes para esta función (llamadas adelantadas),
        # se parcha ahora su destino.
        for gosub_index in self.pending_gosub_fixups.get(function_name, []):
            self.context.quadruples.update_result(
                gosub_index,
                self.function_start_indices[function_name],
            )
        # Ya no quedan pendientes para esta función
        self.pending_gosub_fixups[function_name] = []

        self._generate_estatutos(estatutos_tree)

        end_index = self.context.quadruples.enqueue(
            Quadruple("ENDFUNC", function_name, None, None)
        )

        # Cualquier 'return' dentro de esta función salta a ENDFUNC
        for goto_index in self.pending_return_gotos.get(function_name, []):
            self.context.quadruples.update_result(goto_index, end_index)

        self.current_function_name = previous_function_name

    # Cuerpo principal y estatutos
    def _generate_cuerpo_principal(self, cuerpo_principal_tree: Tree) -> None:
        """cuerpo_principal: INICIO LLAVE_IZQ estatutos LLAVE_DER FIN"""
        for child in cuerpo_principal_tree.children:
            if isinstance(child, Tree) and child.data == "estatutos":
                self._generate_estatutos(child)

    def _generate_cuerpo(self, cuerpo_tree: Tree) -> None:
        """cuerpo: LLAVE_IZQ estatutos LLAVE_DER"""
        for child in cuerpo_tree.children:
            if isinstance(child, Tree) and child.data == "estatutos":
                self._generate_estatutos(child)

    def _generate_estatutos(self, estatutos_tree: Tree) -> None:
        """estatutos: estatuto*"""
        for child in estatutos_tree.children:
            if isinstance(child, Tree) and child.data == "estatuto":
                self._generate_estatuto(child)

    def _generate_estatuto(self, estatuto_tree: Tree) -> None:
        """
        estatuto: asignacion | condicion | ciclo | llamada_func | imprime | retorno | bloque_anidado
        """
        for child in estatuto_tree.children:
            if not isinstance(child, Tree):
                continue

            if child.data == "asignacion":
                self._generate_asignacion(child)
            elif child.data == "condicion":
                self._generate_condicion(child)
            elif child.data == "ciclo":
                self._generate_ciclo(child)
            elif child.data == "llamada_func":
                self._generate_llamada_func(child)
            elif child.data == "imprime":
                self._generate_imprime(child)
            elif child.data == "retorno":
                self._generate_retorno(child)
            elif child.data == "bloque_anidado":
                self._generate_bloque_anidado(child)

    def _generate_bloque_anidado(self, bloque_anidado_tree: Tree) -> None:
        """bloque_anidado: CORCHETE_IZQ estatutos CORCHETE_DER"""
        for child in bloque_anidado_tree.children:
            if isinstance(child, Tree) and child.data == "estatutos":
                self._generate_estatutos(child)

    def _generate_asignacion(self, asignacion_tree: Tree) -> None:
        """
        asignacion: ID ASIGNA expresion PUNTO_COMA
        """
        children = asignacion_tree.children

        # 1) Variable destino (ID)
        variable_token = children[0]
        if not isinstance(variable_token, Token) or variable_token.type != "ID":
            raise ValueError("Primer hijo de 'asignacion' debe ser ID.")
        variable_name = variable_token.value

        variable_info = self.function_directory.lookup_variable(
            variable_name=variable_name,
            current_function_name=self.current_function_name,
        )
        left_type: TypeName = variable_info.var_type

        # 2) Busca la expresión del lado derecho
        expresion_tree: Optional[Tree] = None
        for child in children:
            if isinstance(child, Tree) and child.data == "expresion":
                expresion_tree = child
                break

        if expresion_tree is None:
            raise ValueError("asignacion sin expresión del lado derecho.")

        # 3) Genera cuádruplos para la expresión
        expresion_result = self._generate_expresion(expresion_tree)
        right_type: TypeName = expresion_result.result_type

        # 4) Validación de tipos
        assert_assign(left_type, right_type, context="asignacion")

        # 5) Cuádruplo ASSIGN usando direcciones virtuales
        if variable_info.virtual_address is None:
            raise SemanticError(
                f"Variable '{variable_name}' no tiene dirección virtual asignada."
            )

        self.context.quadruples.enqueue(
            Quadruple(
                "ASSIGN",
                expresion_result.address, # dirección del valor calculado
                None,
                variable_info.virtual_address, # dirección de la variable destino
            )
        )

    def _generate_imprime(self, imprime_tree: Tree) -> None:
        """
        imprime: ESCRIBE PAREN_IZQ args_imprime PAREN_DER PUNTO_COMA
        args_imprime: (expresion (COMA expresion)*) | (CTE_STRING (COMA expresion)?)
        """
        args_imprime_tree: Optional[Tree] = None

        # Localiza el nodo args_imprime
        for child in imprime_tree.children:
            if isinstance(child, Tree) and child.data == "args_imprime":
                args_imprime_tree = child
                break

        if args_imprime_tree is None:
            raise ValueError("imprime sin args_imprime.")

        children = args_imprime_tree.children

        # Caso 1: escribe("texto") - solo string
        if (
            len(children) == 1
            and isinstance(children[0], Token)
            and children[0].type == "CTE_STRING"
        ):
            string_token = children[0]
            # Guarda el string en el segmento de constantes STRING
            string_address = self.virtual_memory.allocate_constant(
                string_token.value,
                "STRING", # Tipo lógico para strings en la tabla de constantes
            )
            self.context.quadruples.enqueue(
                Quadruple("PRINT", string_address, None, None)
            )
            return

        # Caso 2: escribe(expr) o escribe(expr, expr, ...)
        # Procesa cada hijo que sea una expresión
        for child in children:
            if isinstance(child, Tree) and child.data == "expresion":
                expr_result = self._generate_expresion(child)
                self.context.quadruples.enqueue(
                    Quadruple("PRINT", expr_result.address, None, None)
                )
            elif isinstance(child, Token) and child.type == "CTE_STRING":
                string_address = self.virtual_memory.allocate_constant(
                    child.value,
                    "STRING",
                )
                self.context.quadruples.enqueue(
                    Quadruple("PRINT", string_address, None, None)
                )

    def _prepare_function_call(self, function_name: str, args_tree: Optional[Tree]):
        """
        Valida número y tipos de argumentos para una llamada a función.
        Regresa:
        - function_info: metadatos de la función (tipo de retorno, parámetros).
        - argument_results: lista de ExpressionResult de cada argumento en orden.
        """
        function_info = self.function_directory.get_function(function_name)
        parameter_list = function_info.parameter_list

        # Si no hay nodo args (funciones sin parámetros)
        if args_tree is None or not isinstance(args_tree, Tree):
            argument_results: List[ExpressionResult] = []
        else:
            argument_results = self._generate_args(args_tree)

        expected_count = len(parameter_list)
        given_count = len(argument_results)

        if expected_count != given_count:
            raise SemanticError(
                f"Llamada a función '{function_name}' con {given_count} argumentos, "
                f"pero se esperaban {expected_count}."
            )

        # Validación de tipos
        for position, (arg_result, param_info) in enumerate(
            zip(argument_results, parameter_list),
            start=1,
        ):
            assert_assign(
                left_type=param_info.var_type,
                right_type=arg_result.result_type,
                context=f"argumento {position} de '{function_name}'",
            )

        return function_info, argument_results

    def _emit_function_activation(self, function_info, argument_results: List["ExpressionResult"]) -> None:
        """
        Genera los cuádruplos ERA, PARAM y GOSUB para una llamada a función.
        """
        function_name = function_info.name

        # ERA: prepara el activation record de la función
        self.context.quadruples.enqueue(
            Quadruple("ERA", function_name, None, None)
        )

        # PARAM: manda cada argumento en orden
        for position, arg_result in enumerate(argument_results, start=1):
            self.context.quadruples.enqueue(
                Quadruple("PARAM", arg_result.address, None, position)
            )

        # GOSUB: salto a la función
        start_index = self.function_start_indices.get(function_name)
        gosub_index = self.context.quadruples.enqueue(
            Quadruple("GOSUB", function_name, None, start_index)
        )

        # Si todavía no se sabe dónde inicia la función (llamada adelantada),
        # guarda este GOSUB para parcharlo cuando se procese el func_decl.
        if start_index is None:
            self.pending_gosub_fixups.setdefault(function_name, []).append(gosub_index)

    def _generate_llamada_func(self, llamada_func_tree: Tree) -> None:
        """
        llamada_func: ID PAREN_IZQ args? PAREN_DER PUNTO_COMA
        """
        function_name: Optional[str] = None
        args_tree: Optional[Tree] = None

        # Extrae el nombre de la función y el nodo args
        for child in llamada_func_tree.children:
            if isinstance(child, Token) and child.type == "ID":
                function_name = child.value
            elif isinstance(child, Tree) and child.data == "args":
                args_tree = child

        if function_name is None:
            raise ValueError("llamada_func sin nombre de función.")

        # Prepara y valida la llamada
        function_info, argument_results = self._prepare_function_call(function_name, args_tree)

        # Genera ERA, PARAM, GOSUB.
        self._emit_function_activation(function_info, argument_results)

    def _generate_args(self, args_tree: Tree) -> List[ExpressionResult]:
        """
        args: expresion (COMA expresion)*
        """
        children = args_tree.children
        results: List[ExpressionResult] = []

        # Patrón: expr, COMA, expr, COMA, ...
        for index in range(0, len(children), 2):
            expr_node = children[index]
            if not isinstance(expr_node, Tree) or expr_node.data != "expresion":
                raise ValueError("Se esperaba Tree('expresion') en args.")
            results.append(self._generate_expresion(expr_node))

        return results

    def _generate_retorno(self, retorno_tree: Tree) -> None:
        """
        retorno: RETURN expresion? PUNTO_COMA

        Genera el código para un 'return' dentro de una función:
        - Valida el tipo usando assert_return.
        - Si la función tiene tipo, copia el valor a su slot de retorno.
        - Genera un GOTO de salida al final de la función.
        """
        if self.current_function_name is None:
            # No se encuentra dentro de ninguna función (cuerpo principal)
            raise SemanticError("El estatuto 'return' solo puede usarse dentro de una función.")

        # Localiza en caso de existir la expresión del return
        expresion_tree: Optional[Tree] = None
        for child in retorno_tree.children:
            if isinstance(child, Tree) and child.data == "expresion":
                expresion_tree = child
                break

        expresion_result: Optional[ExpressionResult] = None
        expr_type: Optional[TypeName]

        if expresion_tree is not None:
            expresion_result = self._generate_expresion(expresion_tree)
            expr_type = expresion_result.result_type
        else:
            expr_type = None

        # Validación de tipos contra el tipo de retorno de la función actual
        assert_return(
            function_directory=self.function_directory,
            current_function_name=self.current_function_name,
            expression_type=expr_type,
        )

        # Revisa el tipo de la función
        function_info = self.function_directory.get_function(self.current_function_name)

        # Si la función tiene tipo (INT/FLOAT), debe copiar el valor al slot de retorno
        if function_info.return_type != VOID:
            if expresion_result is None:
                # Esto no debería pasar porque assert_return ya habría tronado antes,
                # pero dejamos el check por claridad.
                raise SemanticError(
                    f"La función '{function_info.name}' debe regresar un valor."
                )

            # Dirección global reservada para el valor de retorno de esta función
            ret_address = self.virtual_memory.get_function_return_address(function_info.name)

            # Generar ASSIGN expr -> ret_address
            self.context.quadruples.enqueue(
                Quadruple(
                    "ASSIGN",
                    expresion_result.address,
                    None,
                    ret_address,
                )
            )

        # En cualquier caso, se genera un GOTO de salida.
        goto_index = self.context.quadruples.enqueue(
            Quadruple("GOTO", None, None, None)
        )
        self.pending_return_gotos.setdefault(self.current_function_name, []).append(goto_index)

    # Estatutos no lineales: si / sino y mientras
    def _generate_condicion(self, condicion_tree: Tree) -> None:
        """
        condicion: SI PAREN_IZQ expresion PAREN_DER cuerpo (SINO cuerpo)? PUNTO_COMA
        """
        children = condicion_tree.children

        # Localiza expresion y los cuerpo
        expresion_tree: Optional[Tree] = None
        cuerpo_nodes: List[Tree] = []

        for child in children:
            if isinstance(child, Tree):
                if child.data == "expresion":
                    expresion_tree = child
                elif child.data == "cuerpo":
                    cuerpo_nodes.append(child)

        if expresion_tree is None or not cuerpo_nodes:
            raise ValueError("condicion mal formada (falta expresión o cuerpo).")

        then_cuerpo_tree = cuerpo_nodes[0]
        else_cuerpo_tree = cuerpo_nodes[1] if len(cuerpo_nodes) > 1 else None

        # Genera código para la condición
        condicion_result = self._generate_expresion(expresion_tree)
        ensure_bool(condicion_result.result_type, context="si condicion")

        # GOTOF cond, -, destino (se rellena después)
        gotof_index = len(self.context.quadruples)
        self.context.quadruples.enqueue(
            Quadruple("GOTOF", condicion_result.address, None, None)
        )

        # THEN
        self._generate_cuerpo(then_cuerpo_tree)

        if else_cuerpo_tree is not None:
            # GOTO para saltar el sino al final del si
            goto_end_index = len(self.context.quadruples)
            self.context.quadruples.enqueue(
                Quadruple("GOTO", None, None, None)
            )

            # Rellena el GOTOF para que apunte al inicio del sino
            else_start_index = len(self.context.quadruples)
            self.context.quadruples.update_result(gotof_index, else_start_index)

            # ELSE
            self._generate_cuerpo(else_cuerpo_tree)

            # Rellena el GOTO de salida del si/sino
            end_index = len(self.context.quadruples)
            self.context.quadruples.update_result(goto_end_index, end_index)
        else:
            # No hay sino: GOTOF salta directo al final
            end_index = len(self.context.quadruples)
            self.context.quadruples.update_result(gotof_index, end_index)

    def _generate_ciclo(self, ciclo_tree: Tree) -> None:
        """
        ciclo: MIENTRAS PAREN_IZQ expresion PAREN_DER HAZ cuerpo PUNTO_COMA
        """
        children = ciclo_tree.children

        # Inicio del ciclo
        loop_start_index = len(self.context.quadruples)

        # Busca expresión y cuerpo
        expresion_tree: Optional[Tree] = None
        cuerpo_tree: Optional[Tree] = None

        for child in children:
            if isinstance(child, Tree):
                if child.data == "expresion":
                    expresion_tree = child
                elif child.data == "cuerpo":
                    cuerpo_tree = child

        if expresion_tree is None or cuerpo_tree is None:
            raise ValueError("ciclo mal formado (falta expresión o cuerpo).")

        condicion_result = self._generate_expresion(expresion_tree)
        ensure_bool(condicion_result.result_type, context="mientras condicion")

        # GOTOF cond, -, destino_salida (se rellena después)
        gotof_index = len(self.context.quadruples)
        self.context.quadruples.enqueue(
            Quadruple("GOTOF", condicion_result.address, None, None)
        )

        # Cuerpo del ciclo
        self._generate_cuerpo(cuerpo_tree)

        # GOTO de vuelta al inicio
        self.context.quadruples.enqueue(
            Quadruple("GOTO", None, None, loop_start_index)
        )

        # Salida del ciclo
        end_index = len(self.context.quadruples)
        self.context.quadruples.update_result(gotof_index, end_index)

    def _generate_expresion(self, expresion_tree: Tree) -> ExpressionResult:
        """
        expresion: exp_simple cola_relacional?
        cola_relacional: (MAYOR | MENOR | DIFERENTE | IGUAL) exp_simple
        """
        children = expresion_tree.children

        exp_simple_tree = children[0]
        left_result = self._generate_exp_simple(exp_simple_tree)

        # Sin cola_relacional: sólo expresión aritmética
        if len(children) == 1:
            return left_result

        # Hay comparación relacional
        cola_relacional_tree = children[1]

        # En la gramática actual cola_relacional siempre puede existir pero estar vacío.
        if not isinstance(cola_relacional_tree, Tree) or not cola_relacional_tree.children:
            return left_result

        operator_token = cola_relacional_tree.children[0]
        right_exp_simple_tree = cola_relacional_tree.children[1]

        operator_name = operator_token.type  # MAYOR, MENOR, DIFERENTE, IGUAL
        right_result = self._generate_exp_simple(right_exp_simple_tree)

        # Usamos las pilas para generar el cuádruplo relacional
        comparison_result = self._emit_binary_operation(
            operator_name,
            left_result,
            right_result,
        )

        # La comparación debe ser booleana
        ensure_bool(comparison_result.result_type, context="expresion relacional")

        return comparison_result
    
    def _generate_exp_simple(self, exp_simple_tree: Tree) -> ExpressionResult:
        """
        exp_simple: termino ((MAS | MENOS) termino)*
        """
        children = exp_simple_tree.children

        # Primer término
        current_result = self._generate_termino(children[0])

        index = 1
        while index < len(children):
            operator_token = children[index]
            right_termino_tree = children[index + 1]

            operator_name = operator_token.type  # MAS o MENOS
            right_result = self._generate_termino(right_termino_tree)

            # Genera el cuádruplo utilizando las pilas
            current_result = self._emit_binary_operation(
                operator_name,
                current_result,
                right_result,
            )

            index += 2

        return current_result

    def _generate_termino(self, termino_tree: Tree) -> ExpressionResult:
        """
        termino: factor ((POR | ENTRE) factor)*
        """
        children = termino_tree.children

        current_result = self._generate_factor(children[0])

        index = 1
        while index < len(children):
            operator_token = children[index]
            right_factor_tree = children[index + 1]

            operator_name = operator_token.type  # POR o ENTRE
            right_result = self._generate_factor(right_factor_tree)

            # Genera el cuádruplo utilizando las pilas
            current_result = self._emit_binary_operation(
                operator_name,
                current_result,
                right_result,
            )

            index += 2

        return current_result
    
    def _generate_function_call_expression(
        self,
        function_name: str,
        args_tree: Optional[Tree],
    ) -> ExpressionResult:
        """
        Genera cuádruplos para una llamada a función usada en una expresión,
        - Usa ERA / PARAM / GOSUB.
        - Toma el valor de retorno de la función desde su dirección reservada
        en memoria virtual.
        - Copia ese valor a un temporal y regresa un ExpressionResult.
        """
        function_info, argument_results = self._prepare_function_call(function_name, args_tree)

        if function_info.return_type == VOID:
            raise SemanticError(
                f"No se puede usar la función VOID '{function_name}' en una expresión."
            )

        # ERA, PARAM, GOSUB
        self._emit_function_activation(function_info, argument_results)

        # Dirección donde la función deja su valor de retorno
        ret_address = self.virtual_memory.get_function_return_address(function_name)

        # Copiar el valor de retorno a un temporal para usarlo en la expresión
        temp_address = self.virtual_memory.allocate_temporary(function_info.return_type)
        self.context.quadruples.enqueue(
            Quadruple("ASSIGN", ret_address, None, temp_address)
        )

        return ExpressionResult(temp_address, function_info.return_type)

    def _generate_factor(self, factor_tree: Tree) -> ExpressionResult:
        """
        factor: signo? primario
        """
        children = factor_tree.children

        # Caso sin signo: solo primario
        if len(children) == 1:
            primario_tree = children[0]
            # Verificar si es directamente un primario o una expresión entre paréntesis
            if isinstance(primario_tree, Tree):
                if primario_tree.data == "primario":
                    return self._generate_primario(primario_tree)
                elif primario_tree.data == "expresion":
                    # Caso paréntesis: PAREN_IZQ expresion PAREN_DER
                    return self._generate_expresion(primario_tree)
            raise ValueError(f"Forma inesperada de factor (1 hijo): {children!r}")

        # Caso con signo: signo primario
        if len(children) == 2:
            signo_tree = children[0]
            primario_tree = children[1]

            primario_result = self._generate_primario(primario_tree)

            # Extrae el token del signo
            sign_token: Optional[Token] = (
                signo_tree.children[0] if isinstance(signo_tree, Tree) and signo_tree.children else None
            )

            # Sin signo o '+' (MAS)
            if sign_token is None or sign_token.type == "MAS":
                return primario_result

            # Signo '-' (MENOS): genera UMINUS
            if sign_token.type == "MENOS":
                # Pide un temporal del mismo tipo que el primario
                temp_address = self.virtual_memory.allocate_temporary(primario_result.result_type)

                # Genera el cuádruplo UMINUS usando direcciones
                self.context.quadruples.enqueue(
                    Quadruple("UMINUS", primario_result.address, None, temp_address)
                )

                return ExpressionResult(temp_address, primario_result.result_type)

        # Caso especial: paréntesis en el árbol (PAREN_IZQ expresion PAREN_DER)
        if len(children) == 3:
            if (isinstance(children[0], Token) and children[0].type == "PAREN_IZQ" and
                isinstance(children[2], Token) and children[2].type == "PAREN_DER"):
                expresion_tree = children[1]
                return self._generate_expresion(expresion_tree)

        raise ValueError(f"Forma inesperada de factor: {children!r}")

    def _generate_primario(self, primario_tree: Tree) -> ExpressionResult:
        """
        primario: PAREN_IZQ expresion PAREN_DER | constante | ID sufijo_llamada?
        """
        child = primario_tree.children[0]

        # Caso paréntesis: PAREN_IZQ expresion PAREN_DER
        if isinstance(child, Token) and child.type == "PAREN_IZQ":
            expresion_tree = primario_tree.children[1]
            return self._generate_expresion(expresion_tree)

        # Caso constante
        if isinstance(child, Tree) and child.data == "constante":
            return self._generate_constante(child)

        # Caso ID: puede ser variable o función
        if isinstance(child, Token) and child.type == "ID":
            identifier_name = child.value

            # Verifica si hay un sufijo_llamada (función llamada en expresión)
            if len(primario_tree.children) >= 2:
                sufijo_llamada_tree = primario_tree.children[1]
                if isinstance(sufijo_llamada_tree, Tree) and sufijo_llamada_tree.data == "sufijo_llamada":
                    # Es una llamada a función como expresión
                    # sufijo_llamada contiene PAREN_IZQ args? PAREN_DER
                    args_tree = None
                    for suffix_child in sufijo_llamada_tree.children:
                        if isinstance(suffix_child, Tree) and suffix_child.data == "args":
                            args_tree = suffix_child
                            break

                    return self._generate_function_call_expression(identifier_name, args_tree)

            # No hay sufijo_llamada: es una variable
            variable_info = self.function_directory.lookup_variable(
                variable_name=identifier_name,
                current_function_name=self.current_function_name,
            )

            # Debe tener una dirección virtual asignada
            if variable_info.virtual_address is None:
                raise SemanticError(
                    f"Variable '{identifier_name}' no tiene dirección virtual asignada."
                )

            return ExpressionResult(variable_info.virtual_address, variable_info.var_type)

        raise ValueError(f"Forma inesperada de primario: {primario_tree.children!r}")

    def _generate_constante(self, constante_tree: Tree) -> ExpressionResult:
        """
        constante: CTE_INT | CTE_FLOAT
        """
        token = constante_tree.children[0]
        if not isinstance(token, Token):
            raise ValueError("constante debe contener un token literal.")

        # CTE_INT -> segmento de constantes enteras
        if token.type == "CTE_INT":
            address = self.virtual_memory.allocate_constant(token.value, INT)
            return ExpressionResult(address, INT)

        # CTE_FLOAT -> segmento de constantes flotantes
        if token.type == "CTE_FLOAT":
            address = self.virtual_memory.allocate_constant(token.value, FLOAT)
            return ExpressionResult(address, FLOAT)

        raise ValueError(f"Token inesperado en constante: {token!r}")
