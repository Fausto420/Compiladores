from lark.exceptions import UnexpectedInput
from parse_and_scan import parse, scan

DEMO = """\
program demo;
vars:
  x, y: int;
  z: float;
void foo(a: int) [
  vars:
    t: int;
  { print(a, "echo"); }
];
main {
  x = 10;
  y = 1 + 2 * 3;
  if (y == 7) { print(y, "is seven"); };
  while (y > 0) do { y = y - 1; };
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
