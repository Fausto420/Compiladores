from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError
from intermediate_code_structures import IntermediateCodeContext
from expression_to_quads import ExpressionQuadrupleGenerator
from virtual_memory import VirtualMemory, assign_variable_addresses

DEMO = """
program demo;
vars:
    x, y, result: int;
    pi, area: float;

int square(n: int) [
    {
        return n * n;
    }
];

int abs(value: int) [
    {
        if (value < 0) {
            return -value;
        } else {
            return value;
        };
    }
];

float circleArea(radius: float) [
    {
        return radius * radius;
    }
];

int max(a: int, b: int) [
    {
        if (a > b) {
            return a;
        } else {
            return b;
        };
    }
];

void printMessage(code: int) [
    {
        if (code == 0) {
            print("Success");
            return;
        };
        print("Error");
    }
];

main {
    x = 5;
    y = -3;

    result = square(x);
    print(result, "square of 5");

    result = abs(y);
    print(result, "absolute value");

    result = max(x, y);
    print(result, "maximum");

    pi = 3.14;
    area = circleArea(pi);
    print(area, "area");

    result = square(x) + abs(y);
    print(result, "combined expression");

    printMessage(0);
    printMessage(1);
}
end
"""

def main() -> None:
    try:
        # 1) Construye el árbol sintáctico con Lark
        parse_tree = parse(DEMO)

        # 2) Construye las tablas semánticas (directorios de variables y funciones)
        function_directory = build_symbol_tables(parse, DEMO)

        # 3) Crea la memoria virtual y asigna direcciones a TODAS las variables
        #    (globales, locales y parámetros) usando el FunctionDirectory.
        virtual_memory = VirtualMemory()
        assign_variable_addresses(function_directory, virtual_memory)

        # 4) Crea el contexto de código intermedio (pilas + lista de cuádruplos)
        context = IntermediateCodeContext()

        # 5) Crea el generador de cuádruplos usando la MISMA memoria virtual
        #    donde ya se asignaron direcciones a las variables.
        generator = ExpressionQuadrupleGenerator(
            function_directory=function_directory,
            context=context,
            virtual_memory=virtual_memory,
        )

        # 6) Genera los cuádruplos para todo el programa
        generator.generate_program(parse_tree)

        # 7) Imprime los cuádruplos resultantes
        print("CUÁDRUPLOS GENERADOS:\n")
        context.quadruples.pretty_print()

    except SemanticError as error:
        print(f"Error semántico: {error}")

    except Exception as error:
        print("Ocurrió un error inesperado durante la generación de cuádruplos:")
        print(error)


if __name__ == "__main__":
    main()