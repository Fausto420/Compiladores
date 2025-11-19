from pprint import pprint

from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError

DEMO = """\
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
