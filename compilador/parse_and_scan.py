from lark import Lark, UnexpectedInput

PARSER = Lark.open(
    "grammar.lark",
    parser="lalr",
    start="start",
    lexer="contextual",
)

def scan(source: str):
    "Devuelve una lista de tokens. Lanza error si hay mala sintaxis."
    return [(tok.type, tok.value) for tok in PARSER.lex(source)]

def parse(source: str):
    "Devuelve el árbol de parseo. Lanza error si hay mala sintaxis."
    return PARSER.parse(source)

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

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) > 1:
        code_path = Path(sys.argv[1])
        code = code_path.read_text(encoding="utf-8")
    else:
        code = DEMO

    print("TOKENS")
    try:
        for ttype, value in scan(code):
            print(f"({ttype}, {value!r})")
    except UnexpectedInput as e:
        print("\n[Error de escaneo]", e)
        sys.exit(1)

    print("\nPARSE TREE")
    try:
        tree = parse(code)
        print(tree.pretty())
    except UnexpectedInput as e:
        print("\n[Error de sintaxis]")
        print(e)
        sys.exit(1)