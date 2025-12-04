from lark import Lark, UnexpectedInput

PARSER = Lark.open(
    "grammar.lark",
    parser="lalr",
    start="program",
    lexer="contextual",
)

def scan(source: str):
    "Devuelve una lista de tokens. Lanza error si hay mala sintaxis."
    return [(tok.type, tok.value) for tok in PARSER.lex(source)]

def parse(source: str):
    "Devuelve el árbol de parseo. Lanza error si hay mala sintaxis."
    return PARSER.parse(source)

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