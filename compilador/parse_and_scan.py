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

DEMO_CODE = """\
program demo;
vars:
  x, y: int;
  z: float;
void foo(a: int) [
  vars:
    t: int;
  {
    print(a, "echo");
  }
];
main {
  x = 10;
  y = 1 + 2 * 3;
  if (y == 7) { print(y, "is seven"); };
  while (y > 0) do { y = y - 1; };
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
        code = DEMO_CODE

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
