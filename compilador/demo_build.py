from pprint import pprint
from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError

DEMO = """
programa demo;
vars:
    x, y, result: entero;
    pi, area: flotante;

entero square(n: entero) {
    return n * n;
};

entero abs(value: entero) {
    si (value < 0) {
        return -value;
    } sino {
        return value;
    };
};

flotante circleArea(radius: flotante) {
    return radius * radius;
};

entero max(a: entero, b: entero) {
    si (a > b) {
        return a;
    } sino {
        return b;
    };
};

nula printMessage(code: entero) {
    si (code == 0) {
        escribe("Success");
        return;
    };
    escribe("Error");
};

inicio {
    x = 5;
    y = -3;

    result = square(x);
    escribe(result);

    result = abs(y);
    escribe(result);

    result = max(x, y);
    escribe(result);

    pi = 3.14;
    area = circleArea(pi);
    escribe(area);

    result = square(x) + abs(y);
    escribe(result);

    printMessage(0);
    printMessage(1);
}
fin
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
