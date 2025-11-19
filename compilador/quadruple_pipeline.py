"""
Pipeline sencillo para generar cuádruplos a partir de código fuente Patito.

Pasos:
1. Parsear el código con Lark (ya lo hace parse_and_scan.parse).
2. Construir las tablas semánticas con SemanticBuilder (builder.build_symbol_tables).
3. Crear un IntermediateCodeContext con pilas + fila de cuádruplos.
4. Aplicar ExpressionQuadrupleGenerator sobre el árbol para llenar la fila.
"""

from parse_and_scan import parse
from builder import build_symbol_tables
from intermediate_code_structures import IntermediateCodeContext
from expression_to_quads import ExpressionQuadrupleGenerator


def generate_quadruples(source_code: str) -> IntermediateCodeContext:
    """
    Dado un programa en el lenguaje Patito (como cadena),
    genera su código intermedio en forma de cuádruplos.

    Regresa el IntermediateCodeContext, que contiene:
    - operator_stack, operand_stack, type_stack
    - quadruples (fila de cuádruplos)
    """
    # 1) Construimos el árbol de parseo del programa
    parse_tree = parse(source_code)

    # 2) Construimos las tablas semánticas (variables, funciones, tipos)
    #    Nota: build_symbol_tables internamente también parsea,
    #    no pasa nada si se vuelve a hacer parse porque el proyecto es pequeño.
    function_directory = build_symbol_tables(parse, source_code)

    # 3) Creamos el contexto de código intermedio
    context = IntermediateCodeContext()

    # 4) Creamos el generador de cuádruplos para expresiones + asignaciones
    expression_generator = ExpressionQuadrupleGenerator(
        context=context,
        function_directory=function_directory,
        current_function_name=None,  # por ahora asumimos solo variables globales
    )

    # 5) Recorremos TODO el árbol del programa.
    #    ExpressionQuadrupleGenerator solo actuará en las reglas que conoce:
    #    - number, primary, factor, term, simple_expr, expression, rel_tail
    #    - assign_stat
    expression_generator.transform(parse_tree)

    # 6) Regresamos el contexto ya lleno de cuádruplos
    return context
