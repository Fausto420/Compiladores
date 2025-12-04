from pprint import pprint
from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError

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

def main():
    try:
        # 1. Construye el directorio de funciones y las tablas de variables
        function_directory = build_symbol_tables(parse, DEMO)
    except SemanticError as error:
        print("Error semántico:", error)
        return

    # 2. Imprime el resultado en formato diccionario para verlo claro
    print("\nDIRECTORIO DE FUNCIONES Y TABLAS DE VARIABLES:\n")
    pprint(function_directory.to_dict())


if __name__ == "__main__":
    main()
