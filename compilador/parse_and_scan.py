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
    c = a + b * 2;
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