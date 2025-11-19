from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError
from intermediate_code_structures import IntermediateCodeContext
from expression_to_quads import ExpressionQuadrupleGenerator

DEMO = """
program demo;
vars:
    a, b, c: int;
    x: float;

void foo(p: int, q: float) [
    vars:
        tmp: int;
    {
        print("in foo");
    }
];

main {
    a = 2;
    b = 3;
    c = a + b * 4;
    print(c, " result");

    if (c > 10) {
        print("big");
    } else {
        print("small");
    };

    while (c < 20) do {
        c = c + 1;
    };

    foo(c, x);
}
end
"""

def main() -> None:
    try:
        # 1) Construye el árbol sintáctico con Lark
        parse_tree = parse(DEMO)

        # 2) Construye las tablas semánticas (directorios de variables y funciones)
        function_directory = build_symbol_tables(parse, DEMO)

        # 3) Crea el contexto de código intermedio
        context = IntermediateCodeContext()

        # 4) Crea el generador de cuádruplos y procesa el programa
        generator = ExpressionQuadrupleGenerator(
            function_directory=function_directory,
            context=context,
        )

        generator.generate_program(parse_tree)

        # 5) Imprime los cuádruplos resultantes
        print("CUÁDRUPLOS GENERADOS:\n")
        context.quadruples.pretty_print()

    except SemanticError as error:
        print(f"Error semántico: {error}")

    except Exception as error:
        print("Ocurrió un error inesperado durante la generación de cuádruplos:")
        print(error)


if __name__ == "__main__":
    main()
