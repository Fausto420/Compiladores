from parse_and_scan import parse
from builder import build_symbol_tables
from intermediate_code_structures import IntermediateCodeContext
from expression_to_quads import ExpressionQuadrupleGenerator


def generate_quadruples(source_code: str) -> IntermediateCodeContext:
    """
    Genera el código intermedio en forma de cuádruplos.

    Regresa un IntermediateCodeContext, que contiene:
    - operator_stack, operand_stack, type_stack
    - quadruples (fila de cuádruplos)
    """
    # 1) Árbol de parseo del programa
    parse_tree = parse(source_code)

    # 2) Directorio de funciones y variables (semántica de la entrega 2)
    function_directory = build_symbol_tables(parse, source_code)

    # 3) Contexto de código intermedio
    context = IntermediateCodeContext()

    # 4) Generador de cuádruplos para expresiones + estatutos
    generator = ExpressionQuadrupleGenerator(
        function_directory=function_directory,
        context=context,
    )

    # 5) Recorre el árbol completo del programa
    generator.generate_program(parse_tree)

    # 6) Regresa el contexto ya lleno de cuádruplos
    return context
