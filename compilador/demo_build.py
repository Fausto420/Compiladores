from pathlib import Path
from pprint import pprint
from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError


def main():
    # Cargar el código fuente desde el archivo de ejemplo
    demo_path = Path(__file__).parent / "examples" / "demo.patito"
    source_code = demo_path.read_text(encoding="utf-8")

    try:
        # 1. Construye el directorio de funciones y las tablas de variables
        function_directory = build_symbol_tables(parse, source_code)
    except SemanticError as error:
        print("Error semántico:", error)
        return

    # 2. Imprime el resultado en formato diccionario para verlo claro
    print("\nDIRECTORIO DE FUNCIONES Y TABLAS DE VARIABLES:\n")
    pprint(function_directory.to_dict())


if __name__ == "__main__":
    main()
