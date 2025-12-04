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
        Entra al nodo 'program' y genera cuádruplos para todas las funciones de funcs_section y
        el body principal (después de MAIN).
        """
        if not isinstance(program_tree, Tree) or program_tree.data != "program":
            raise ValueError("generate_program espera un Tree('program').")

        # 1) Funciones
        for child in program_tree.children:
            if isinstance(child, Tree) and child.data == "funcs_section":
                self._generate_funcs_section(child)

        # 2) Body principal (MAIN body)
        for child in program_tree.children:
            if isinstance(child, Tree) and child.data == "body":
                self.current_function_name = None
                self._generate_body(child)

        return self.context

    def _generate_funcs_section(self, funcs_section_tree: Tree) -> None:
        """funcs_section: func_decl*"""
        for child in funcs_section_tree.children:
            if isinstance(child, Tree) and child.data == "func_decl":
                self._generate_function(child)

    def _generate_function(self, func_decl_tree: Tree) -> None:
        """
        func_decl: func_return_type ID LPAREN params RPAREN LBRACKET vars_section body RBRACKET SEMICOL
        """
        function_name: Optional[str] = None
        body_tree: Optional[Tree] = None

        # Busca el nombre (ID)
        for child in func_decl_tree.children:
            if isinstance(child, Token) and child.type == "ID":
                function_name = child.value
                break

        if function_name is None:
            raise ValueError("func_decl sin ID de función.")

        # Busca el body
        for child in func_decl_tree.children:
            if isinstance(child, Tree) and child.data == "body":
                body_tree = child
                break

        if body_tree is None:
            raise ValueError(f"func_decl de '{function_name}' sin body.")

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

        self._generate_body(body_tree)

        end_index = self.context.quadruples.enqueue(
            Quadruple("ENDFUNC", function_name, None, None)
        )

        # Cualquier 'return' dentro de esta función salta a ENDFUNC
        for goto_index in self.pending_return_gotos.get(function_name, []):
            self.context.quadruples.update_result(goto_index, end_index)

        self.current_function_name = previous_function_name

    # BODY y statements
    def _generate_body(self, body_tree: Tree) -> None:
        """body: LBRACE stmt_list RBRACE"""
        for child in body_tree.children:
            if isinstance(child, Tree) and child.data == "stmt_list":
                self._generate_stmt_list(child)

    def _generate_stmt_list(self, stmt_list_tree: Tree) -> None:
        """stmt_list: statement*"""
        for child in stmt_list_tree.children:
            if isinstance(child, Tree) and child.data == "statement":
                self._generate_statement(child)

    def _generate_statement(self, statement_tree: Tree) -> None:
        """
        statement: assign | condition | cycle | fcall | print_stmt | return_stmt | body
        """
        for child in statement_tree.children:
            if not isinstance(child, Tree):
                continue

            if child.data == "assign":
                self._generate_assign(child)
            elif child.data == "condition":
                self._generate_condition(child)
            elif child.data == "cycle":
                self._generate_cycle(child)
            elif child.data == "fcall":
                self._generate_fcall(child)
            elif child.data == "print_stmt":
                self._generate_print_stmt(child)
            elif child.data == "return_stmt":
                self._generate_return_stmt(child)
            elif child.data == "body":
                self._generate_body(child)

    def _generate_assign(self, assign_tree: Tree) -> None:
        """
        assign: ID ASSIGN expression SEMICOL
        """
        children = assign_tree.children

        # 1) Variable destino (ID)
        variable_token = children[0]
        if not isinstance(variable_token, Token) or variable_token.type != "ID":
            raise ValueError("Primer hijo de 'assign' debe ser ID.")
        variable_name = variable_token.value

        variable_info = self.function_directory.lookup_variable(
            variable_name=variable_name,
            current_function_name=self.current_function_name,
        )
        left_type: TypeName = variable_info.var_type

        # 2) Busca la expresión del lado derecho
        expression_tree: Optional[Tree] = None
        for child in children:
            if isinstance(child, Tree) and child.data == "expression":
                expression_tree = child
                break

        if expression_tree is None:
            raise ValueError("assign sin expresión del lado derecho.")

        # 3) Genera cuádruplos para la expresión
        expression_result = self._generate_expression(expression_tree)
        right_type: TypeName = expression_result.result_type

        # 4) Validación de tipos
        assert_assign(left_type, right_type, context="assign")

        # 5) Cuádruplo ASSIGN usando direcciones virtuales
        if variable_info.virtual_address is None:
            raise SemanticError(
                f"Variable '{variable_name}' no tiene dirección virtual asignada."
            )

        self.context.quadruples.enqueue(
            Quadruple(
                "ASSIGN",
                expression_result.address, # dirección del valor calculado
                None,
                variable_info.virtual_address, # dirección de la variable destino
            )
        )

    def _generate_print_stmt(self, print_stmt_tree: Tree) -> None:
        """
        print_stmt: PRINT LPAREN print_args RPAREN SEMICOL
        print_args: CTE_STRING | expression (COMMA CTE_STRING)?
        """
        print_args_tree: Optional[Tree] = None

        # Localiza el nodo print_args
        for child in print_stmt_tree.children:
            if isinstance(child, Tree) and child.data == "print_args":
                print_args_tree = child
                break

        if print_args_tree is None:
            raise ValueError("print_stmt sin print_args.")

        children = print_args_tree.children

        # Caso 1: print("texto")
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

        # Caso 2: print(expr) o print(expr, "texto")
        expression_tree = children[0]
        if not isinstance(expression_tree, Tree) or expression_tree.data != "expression":
            raise ValueError(
                "print_args mal formado: se esperaba expression o CTE_STRING."
            )

        expr_result = self._generate_expression(expression_tree)
        self.context.quadruples.enqueue(
            Quadruple("PRINT", expr_result.address, None, None)
        )

        # Si hay coma y string, lo imprime después
        if len(children) >= 3:
            last = children[-1]
            if isinstance(last, Token) and last.type == "CTE_STRING":
                string_address = self.virtual_memory.allocate_constant(
                    last.value,
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

    def _generate_fcall(self, fcall_tree: Tree) -> None:
        """
        fcall: ID LPAREN args RPAREN SEMICOL
        """
        function_name: Optional[str] = None
        args_tree: Optional[Tree] = None

        # Extrae el nombre de la función y el nodo args
        for child in fcall_tree.children:
            if isinstance(child, Token) and child.type == "ID":
                function_name = child.value
            elif isinstance(child, Tree) and child.data == "args":
                args_tree = child

        if function_name is None:
            raise ValueError("fcall sin nombre de función.")

        # Prepara y valida la llamada
        function_info, argument_results = self._prepare_function_call(function_name, args_tree)

        # Genera ERA, PARAM, GOSUB.
        self._emit_function_activation(function_info, argument_results)

    def _generate_args(self, args_tree: Tree) -> List[ExpressionResult]:
        """
        args: expression (COMMA expression)*
        """
        children = args_tree.children
        results: List[ExpressionResult] = []

        # Patrón: expr, COMMA, expr, COMMA, ...
        for index in range(0, len(children), 2):
            expr_node = children[index]
            if not isinstance(expr_node, Tree) or expr_node.data != "expression":
                raise ValueError("Se esperaba Tree('expression') en args.")
            results.append(self._generate_expression(expr_node))

        return results

    def _generate_return_stmt(self, return_tree: Tree) -> None:
        """
        return_stmt: RETURN expression? SEMICOL

        Genera el código para un 'return' dentro de una función:
        - Valida el tipo usando assert_return.
        - Si la función tiene tipo, copia el valor a su slot de retorno.
        - Genera un GOTO de salida al final de la función.
        """
        if self.current_function_name is None:
            # No se encuentra dentro de ninguna función (cuerpo principal)
            raise SemanticError("El estatuto 'return' solo puede usarse dentro de una función.")

        # Localiza en caso de existir la expresión del return
        expression_tree: Optional[Tree] = None
        for child in return_tree.children:
            if isinstance(child, Tree) and child.data == "expression":
                expression_tree = child
                break

        expression_result: Optional[ExpressionResult] = None
        expr_type: Optional[TypeName]

        if expression_tree is not None:
            expression_result = self._generate_expression(expression_tree)
            expr_type = expression_result.result_type
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
            if expression_result is None:
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
                    expression_result.address,
                    None,
                    ret_address,
                )
            )

        # En cualquier caso, se genera un GOTO de salida.
        goto_index = self.context.quadruples.enqueue(
            Quadruple("GOTO", None, None, None)
        )
        self.pending_return_gotos.setdefault(self.current_function_name, []).append(goto_index)

    # Estatutos no lineales: if / else y while
    def _generate_condition(self, condition_tree: Tree) -> None:
        """
        condition: IF LPAREN expression RPAREN body (ELSE body)? SEMICOL
        """
        children = condition_tree.children

        # Localiza expression y los body
        expression_tree: Optional[Tree] = None
        body_nodes: List[Tree] = []

        for child in children:
            if isinstance(child, Tree):
                if child.data == "expression":
                    expression_tree = child
                elif child.data == "body":
                    body_nodes.append(child)

        if expression_tree is None or not body_nodes:
            raise ValueError("condition mal formada (falta expresión o body).")

        then_body_tree = body_nodes[0]
        else_body_tree = body_nodes[1] if len(body_nodes) > 1 else None

        # Genera código para la condición
        condition_result = self._generate_expression(expression_tree)
        ensure_bool(condition_result.result_type, context="if condition")

        # GOTOF cond, -, destino (se rellena después)
        gotof_index = len(self.context.quadruples)
        self.context.quadruples.enqueue(
            Quadruple("GOTOF", condition_result.address, None, None)
        )

        # THEN
        self._generate_body(then_body_tree)

        if else_body_tree is not None:
            # GOTO para saltar el else al final del if
            goto_end_index = len(self.context.quadruples)
            self.context.quadruples.enqueue(
                Quadruple("GOTO", None, None, None)
            )

            # Rellena el GOTOF para que apunte al inicio del else
            else_start_index = len(self.context.quadruples)
            self.context.quadruples.update_result(gotof_index, else_start_index)

            # ELSE
            self._generate_body(else_body_tree)

            # Rellena el GOTO de salida del if/else
            end_index = len(self.context.quadruples)
            self.context.quadruples.update_result(goto_end_index, end_index)
        else:
            # No hay else: GOTOF salta directo al final
            end_index = len(self.context.quadruples)
            self.context.quadruples.update_result(gotof_index, end_index)

    def _generate_cycle(self, cycle_tree: Tree) -> None:
        """
        cycle: WHILE LPAREN expression RPAREN DO body SEMICOL
        """
        children = cycle_tree.children

        # Inicio del ciclo
        loop_start_index = len(self.context.quadruples)

        # Busca expresión y body
        expression_tree: Optional[Tree] = None
        body_tree: Optional[Tree] = None

        for child in children:
            if isinstance(child, Tree):
                if child.data == "expression":
                    expression_tree = child
                elif child.data == "body":
                    body_tree = child

        if expression_tree is None or body_tree is None:
            raise ValueError("cycle mal formado (falta expresión o body).")

        condition_result = self._generate_expression(expression_tree)
        ensure_bool(condition_result.result_type, context="while condition")

        # GOTOF cond, -, destino_salida (se rellena después)
        gotof_index = len(self.context.quadruples)
        self.context.quadruples.enqueue(
            Quadruple("GOTOF", condition_result.address, None, None)
        )

        # Body del ciclo
        self._generate_body(body_tree)

        # GOTO de vuelta al inicio
        self.context.quadruples.enqueue(
            Quadruple("GOTO", None, None, loop_start_index)
        )

        # Salida del ciclo
        end_index = len(self.context.quadruples)
        self.context.quadruples.update_result(gotof_index, end_index)

    def _generate_expression(self, expression_tree: Tree) -> ExpressionResult:
        """
        expression: simple_expr rel_tail?
        rel_tail: (GREATER | LESS | NOTEQUAL | EQUAL) simple_expr | ε
        """
        children = expression_tree.children

        simple_expr_tree = children[0]
        left_result = self._generate_simple_expr(simple_expr_tree)

        # Sin rel_tail: sólo expresión aritmética
        if len(children) == 1:
            return left_result

        # Hay comparación relacional
        rel_tail_tree = children[1]

        # En la gramática actual rel_tail siempre puede existir pero estar vacío.
        if not isinstance(rel_tail_tree, Tree) or not rel_tail_tree.children:
            return left_result

        operator_token = rel_tail_tree.children[0]
        right_simple_expr_tree = rel_tail_tree.children[1]

        operator_name = operator_token.type  # GREATER, LESS, NOTEQUAL, EQUAL
        right_result = self._generate_simple_expr(right_simple_expr_tree)

        # Usamos las pilas para generar el cuádruplo relacional
        comparison_result = self._emit_binary_operation(
            operator_name,
            left_result,
            right_result,
        )

        # La comparación debe ser booleana
        ensure_bool(comparison_result.result_type, context="relational expression")

        return comparison_result
    
    def _generate_simple_expr(self, simple_expr_tree: Tree) -> ExpressionResult:
        """
        simple_expr: term ((PLUS | MINUS) term)*
        """
        children = simple_expr_tree.children

        # Primer término
        current_result = self._generate_term(children[0])

        index = 1
        while index < len(children):
            operator_token = children[index]
            right_term_tree = children[index + 1]

            operator_name = operator_token.type  # PLUS o MINUS
            right_result = self._generate_term(right_term_tree)

            # Genera el cuádruplo utilizando las pilas
            current_result = self._emit_binary_operation(
                operator_name,
                current_result,
                right_result,
            )

            index += 2

        return current_result

    def _generate_term(self, term_tree: Tree) -> ExpressionResult:
        """
        term: factor ((STAR | SLASH) factor)*
        """
        children = term_tree.children

        current_result = self._generate_factor(children[0])

        index = 1
        while index < len(children):
            operator_token = children[index]
            right_factor_tree = children[index + 1]

            operator_name = operator_token.type  # STAR o SLASH
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
        factor: LPAREN expression RPAREN | sign_opt primary
        """
        children = factor_tree.children

        # Caso paréntesis: ( expression )
        if (
            len(children) == 3
            and isinstance(children[0], Token) and children[0].type == "LPAREN"
            and isinstance(children[2], Token) and children[2].type == "RPAREN"
        ):
            expression_tree = children[1]
            return self._generate_expression(expression_tree)

        # Caso sign_opt primary
        if len(children) == 2:
            sign_opt_tree = children[0]
            primary_tree = children[1]

            primary_result = self._generate_primary(primary_tree)

            # sign_opt puede venir vacío
            sign_token: Optional[Token] = (
                sign_opt_tree.children[0] if sign_opt_tree.children else None
            )

            # Sin signo o '+'
            if sign_token is None or sign_token.type == "PLUS":
                return primary_result

            # Signo '-': genera UMINUS
            if sign_token.type == "MINUS":
                # Pide un temporal del mismo tipo que el primary
                temp_address = self.virtual_memory.allocate_temporary(primary_result.result_type)

                # Genera el cuádruplo UMINUS usando direcciones
                self.context.quadruples.enqueue(
                    Quadruple("UMINUS", primary_result.address, None, temp_address)
                )

                return ExpressionResult(temp_address, primary_result.result_type)

        raise ValueError(f"Forma inesperada de factor: {children!r}")

    def _generate_primary(self, primary_tree: Tree) -> ExpressionResult:
        """
        primary: ID call_suffix? | number
        """
        child = primary_tree.children[0]

        # Caso ID: puede ser variable o función
        if isinstance(child, Token) and child.type == "ID":
            identifier_name = child.value

            # Verifica si hay un call_suffix (función llamada en expresión)
            if len(primary_tree.children) >= 2:
                call_suffix_tree = primary_tree.children[1]
                if isinstance(call_suffix_tree, Tree) and call_suffix_tree.data == "call_suffix":
                    # Es una llamada a función como expresión
                    # call_suffix contiene LPAREN args RPAREN
                    args_tree = None
                    for suffix_child in call_suffix_tree.children:
                        if isinstance(suffix_child, Tree) and suffix_child.data == "args":
                            args_tree = suffix_child
                            break

                    return self._generate_function_call_expression(identifier_name, args_tree)

            # No hay call_suffix: es una variable
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

        # Caso literal numérico
        if isinstance(child, Tree) and child.data == "number":
            return self._generate_number(child)

        raise ValueError(f"Forma inesperada de primary: {primary_tree.children!r}")

    def _generate_number(self, number_tree: Tree) -> ExpressionResult:
        """
        number: CTE_INT | CTE_FLOAT
        """
        token = number_tree.children[0]
        if not isinstance(token, Token):
            raise ValueError("number debe contener un token literal.")

        # INT -> segmento de constantes enteras
        if token.type == "CTE_INT":
            address = self.virtual_memory.allocate_constant(token.value, INT)
            return ExpressionResult(address, INT)

        # FLOAT -> segmento de constantes flotantes
        if token.type == "CTE_FLOAT":
            address = self.virtual_memory.allocate_constant(token.value, FLOAT)
            return ExpressionResult(address, FLOAT)

        raise ValueError(f"Token inesperado en number: {token!r}")
