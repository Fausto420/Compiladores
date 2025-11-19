from lark.exceptions import UnexpectedInput
from parse_and_scan import parse, scan

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

def test_demo_parses():
    tree = parse(DEMO)
    assert tree is not None

def test_keywords_not_ids():
    kw = "program main end vars void int float if else while do print"
    types = [t[0] for t in scan(kw)]
    assert "ID" not in types

def test_missing_semicolon():
    bad = "program p; vars: x: int; main { x = 1 } end"
    try:
        parse(bad)
        assert False, "Debió fallar por ; faltante"
    except UnexpectedInput:
        assert True

def test_precedence_mult_before_plus():
    tree = parse("program p; vars: x: int; main { x = 1 + 2 * 3; } end")
    s = tree.pretty()
    assert "simple_expr" in s and "term" in s