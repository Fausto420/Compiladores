from dataclasses import dataclass
from typing import Optional, List

from lark import Tree, Token

from semantics import (
    FunctionDirectory,
    TypeName,
    INT,
    FLOAT,
    BOOL,
    result_type,
    assert_assign,
    ensure_bool,
    SemanticError,
)

from intermediate_code_structures import (
    IntermediateCodeContext,
    Quadruple,
)

# Resultado de subexpresiones
@dataclass
class ExpressionResult:
    """
    Representa el resultado de evaluar una subexpresión.
    name: Nombre donde está el valor (variable, constante o temporal).
    result_type: Tipo del valor (INT, FLOAT, BOOL).
    """
    name: str
    result_type: TypeName

# Generador principal de cuádruplos
class ExpressionQuadrupleGenerator:
    """
    Recorre el árbol sintáctico de Lark y llena un IntermediateCodeContext
    con cuádruplos para expresiones aritméticas y relacionales; e
    statutos lineales: assign, print_stmt, fcall; y estatutos no lineales: condition (if/else), cycle (while).
    """

    def __init__(
        self,
        function_directory: FunctionDirectory,
        context: Optional[IntermediateCodeContext] = None,
    ) -> None:
        # Directorio de funciones y variables (builder.py)
        self.function_directory: FunctionDirectory = function_directory

        # Contexto con pilas, temporales y fila de cuádruplos
        self.context: IntermediateCodeContext = (
            context if context is not None else IntermediateCodeContext()
        )

        # Nombre de la función actual (None = cuerpo principal)
        self.current_function_name: Optional[str] = None

    def _emit_binary_operation(
        self,
        operator_name: str,
        left: "ExpressionResult",
        right: "ExpressionResult",
    ) -> "ExpressionResult":

        # 1) Meter operandos + tipos en las pilas
        self.context.push_operand(left.name, left.result_type)
        self.context.push_operand(right.name, right.result_type)
        self.context.push_operator(operator_name)

        # 2) Sacar de las pilas para generar el cuádruplo
        op = self.context.operator_stack.pop()
        right_name = self.context.operand_stack.pop()
        right_type = self.context.type_stack.pop()
        left_name = self.context.operand_stack.pop()
        left_type = self.context.type_stack.pop()

        # Tipo resultante según el cubo semántico
        result_t = result_type(op, left_type, right_type)

        # 3) Crear temporal y cuádruplo
        temp_name = self.context.temporary_generator.new_temporary()
        self.context.quadruples.enqueue(
            Quadruple(op, left_name, right_name, temp_name)
        )

        # 4) Volver a meter el resultado como operando
        self.context.push_operand(temp_name, result_t)

        return ExpressionResult(temp_name, result_t)

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
        func_decl: VOID ID LPAREN params RPAREN LBRACKET vars_section body RBRACKET SEMICOL
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

        # Marca inicio de función
        self.context.quadruples.enqueue(
            Quadruple("BEGINFUNC", function_name, None, None)
        )

        # Genera su body
        self._generate_body(body_tree)

        # Marca fin de función
        self.context.quadruples.enqueue(
            Quadruple("ENDFUNC", function_name, None, None)
        )

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
        statement: assign | condition | cycle | fcall | print_stmt | body
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
            elif child.data == "body":
                self._generate_body(child)

    # Estatutos lineales
    def _generate_assign(self, assign_tree: Tree) -> None:
        """
        assign: ID ASSIGN expression SEMICOL
        """
        children = assign_tree.children

        # Variable destino
        variable_token = children[0]
        if not isinstance(variable_token, Token) or variable_token.type != "ID":
            raise ValueError("Primer hijo de 'assign' debe ser ID.")
        variable_name = variable_token.value

        variable_info = self.function_directory.lookup_variable(
            variable_name=variable_name,
            current_function_name=self.current_function_name,
        )
        left_type: TypeName = variable_info.var_type

        # Expresión del lado derecho (nodo 'expression')
        expression_tree = children[2]
        if not isinstance(expression_tree, Tree) or expression_tree.data != "expression":
            raise ValueError("Tercer hijo de 'assign' debe ser un Tree('expression').")

        expression_result = self._generate_expression(expression_tree)
        right_type: TypeName = expression_result.result_type

        # Validación de tipos
        assert_assign(left_type, right_type, context="assign")

        # Cuádruplo ASSIGN
        self.context.quadruples.enqueue(
            Quadruple("ASSIGN", expression_result.name, None, variable_name)
        )

    def _generate_print_stmt(self, print_stmt_tree: Tree) -> None:
        """
        print_stmt: PRINT LPAREN print_args RPAREN SEMICOL
        print_args: CTE_STRING | expression (COMMA CTE_STRING)?
        """
        print_args_tree: Optional[Tree] = None

        for child in print_stmt_tree.children:
            if isinstance(child, Tree) and child.data == "print_args":
                print_args_tree = child
                break

        if print_args_tree is None:
            raise ValueError("print_stmt sin print_args.")

        children = print_args_tree.children

        # Caso: print("texto");
        if len(children) == 1 and isinstance(children[0], Token) and children[0].type == "CTE_STRING":
            self.context.quadruples.enqueue(
                Quadruple("PRINT", children[0].value, None, None)
            )
            return

        # Caso: print(expr); o print(expr, "texto");
        expression_tree = children[0]
        if not isinstance(expression_tree, Tree) or expression_tree.data != "expression":
            raise ValueError("print_args debe comenzar con un Tree('expression').")

        expr_result = self._generate_expression(expression_tree)
        self.context.quadruples.enqueue(
            Quadruple("PRINT", expr_result.name, None, None)
        )

        # Si hay coma y string, lo imprime después
        if len(children) >= 3:
            last = children[-1]
            if isinstance(last, Token) and last.type == "CTE_STRING":
                self.context.quadruples.enqueue(
                    Quadruple("PRINT", last.value, None, None)
                )

    def _generate_fcall(self, fcall_tree: Tree) -> None:
        """
        fcall: ID LPAREN args RPAREN SEMICOL
        Genera:
            (ARG, valor1, None, 1)
            ...
            (ARG, valorn, None, n)
            (CALL, nombre_función, n, None)
        """
        function_name: Optional[str] = None
        args_tree: Optional[Tree] = None

        for child in fcall_tree.children:
            if isinstance(child, Token) and child.type == "ID":
                function_name = child.value
            elif isinstance(child, Tree) and child.data == "args":
                args_tree = child

        if function_name is None:
            raise ValueError("fcall sin nombre de función.")
        if args_tree is None:
            raise ValueError(f"fcall de '{function_name}' sin args.")

        function_info = self.function_directory.get_function(function_name)
        parameter_list = function_info.parameter_list

        argument_results = self._generate_args(args_tree)

        expected_count = len(parameter_list)
        given_count = len(argument_results)

        if expected_count != given_count:
            raise SemanticError(
                f"Llamada a función '{function_name}' con {given_count} argumentos, "
                f"pero se esperaban {expected_count}."
            )

        # ARG para cada argumento
        for position, (arg_result, param_info) in enumerate(
            zip(argument_results, parameter_list),
            start=1,
        ):
            assert_assign(
                left_type=param_info.var_type,
                right_type=arg_result.result_type,
                context=f"argumento {position} de '{function_name}'",
            )

            self.context.quadruples.enqueue(
                Quadruple("ARG", arg_result.name, None, position)
            )

        # CALL final
        self.context.quadruples.enqueue(
            Quadruple("CALL", function_name, given_count, None)
        )

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

        condition_result = self._generate_expression(expression_tree)
        ensure_bool(condition_result.result_type, context="if condition")

        # GOTOF cond, -, destino (se rellena después)
        gotof_index = len(self.context.quadruples)
        self.context.quadruples.enqueue(
            Quadruple("GOTOF", condition_result.name, None, None)
        )

        # then
        self._generate_body(then_body_tree)

        if else_body_tree is not None:
            # GOTO para saltar el else cuando el if fue verdadero
            goto_end_index = len(self.context.quadruples)
            self.context.quadruples.enqueue(
                Quadruple("GOTO", None, None, None)
            )

            # El else empieza aquí
            else_start_index = len(self.context.quadruples)
            self.context.quadruples.update_result(gotof_index, else_start_index)

            # else
            self._generate_body(else_body_tree)

            # Fin del if/else
            end_index = len(self.context.quadruples)
            self.context.quadruples.update_result(goto_end_index, end_index)
        else:
            # Sin else: GOTOF salta al final del if
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
            if isinstance(child, Tree) and child.data == "expression":
                expression_tree = child
            elif isinstance(child, Tree) and child.data == "body":
                body_tree = child

        if expression_tree is None or body_tree is None:
            raise ValueError("cycle mal formado (falta expresión o body).")

        condition_result = self._generate_expression(expression_tree)
        ensure_bool(condition_result.result_type, context="while condition")

        # GOTOF cond, -, destino_salida (se rellena después)
        gotof_index = len(self.context.quadruples)
        self.context.quadruples.enqueue(
            Quadruple("GOTOF", condition_result.name, None, None)
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
            sign_opt_tree, primary_tree = children

            primary_result = self._generate_primary(primary_tree)

            if not isinstance(sign_opt_tree, Tree) or sign_opt_tree.data != "sign_opt":
                raise ValueError("factor: se esperaba nodo 'sign_opt'.")

            sign_token: Optional[Token] = (
                sign_opt_tree.children[0] if sign_opt_tree.children else None
            )

            # Sin signo o '+'
            if sign_token is None or sign_token.type == "PLUS":
                return primary_result

            # Signo '-': genera UMINUS
            if sign_token.type == "MINUS":
                temp_name = self.context.temporary_generator.new_temporary()
                self.context.quadruples.enqueue(
                    Quadruple("UMINUS", primary_result.name, None, temp_name)
                )
                return ExpressionResult(temp_name, primary_result.result_type)

        raise ValueError(f"Forma inesperada de factor: {children!r}")

    def _generate_primary(self, primary_tree: Tree) -> ExpressionResult:
        """
        primary: ID | number
        """
        child = primary_tree.children[0]

        if isinstance(child, Token) and child.type == "ID":
            variable_name = child.value

            variable_info = self.function_directory.lookup_variable(
                variable_name=variable_name,
                current_function_name=self.current_function_name,
            )

            return ExpressionResult(variable_name, variable_info.var_type)

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

        if token.type == "CTE_INT":
            return ExpressionResult(token.value, INT)
        if token.type == "CTE_FLOAT":
            return ExpressionResult(token.value, FLOAT)

        raise ValueError(f"Token inesperado en number: {token!r}")
