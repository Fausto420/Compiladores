from pprint import pprint

from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError

TEST_PROGRAM = """\
program demo;
vars:
  x, y: int;
  z: float;

void foo(a: int, b: float) [
  vars:
    t: int;
  {
    x = 10;
    t = a;
  }
];

main {
  y = 1 + 2 * 3;
}
end
"""

def main():
    try:
        # 1. Construye el directorio de funciones y las tablas de variables
        function_directory = build_symbol_tables(parse, TEST_PROGRAM)
    except SemanticError as error:
        print("Error semántico:", error)
        return

    # 2. Imprime el resultado en formato diccionario para verlo claro
    print("\nDIRECTORIO DE FUNCIONES Y TABLAS DE VARIABLES:\n")
    pprint(function_directory.to_dict())


if __name__ == "__main__":
    main()
