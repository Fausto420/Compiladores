from parse_and_scan import parse
from builder import build_symbol_tables
from intermediate_code_structures import IntermediateCodeContext
from expression_to_quads import ExpressionQuadrupleGenerator


def generate_quadruples(source_code: str) -> IntermediateCodeContext:
    """
    Genera su código intermedio en forma de cuádruplos.

    Regresa el IntermediateCodeContext, que contiene:
    - operator_stack, operand_stack, type_stack
    - quadruples (fila de cuádruplos)
    """
    # 1) Construye el árbol de parseo del programa
    parse_tree = parse(source_code)

    # 2) Construye las tablas semánticas (variables, funciones, tipos)
    function_directory = build_symbol_tables(parse, source_code)

    # 3) Crea el contexto de código intermedio
    context = IntermediateCodeContext()

    # 4) Crea el generador de cuádruplos para expresiones + asignaciones
    expression_generator = ExpressionQuadrupleGenerator(
        context=context,
        function_directory=function_directory,
        current_function_name=None,  # por ahora se asumen solo variables globales
    )

    # 5) Recorre todo el árbol del programa.
    expression_generator.transform(parse_tree)

    # 6) Regresa el contexto ya lleno de cuádruplos
    return context
