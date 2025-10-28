from lark.exceptions import UnexpectedInput
from parse_and_scan import parse, scan

DEMO = """\
program demo;
var:
  int x, y;
  float z;
void foo(int a) { print(a); }
main {
  x = 10;
  y = x + 3 * 2;
  if (y != 0) { print("ok", y); }
}
end
"""

def test_demo_parses():
    tree = parse(DEMO)
    assert tree is not None

def test_keywords_not_ids():
    types = [t[0] for t in scan("program main end var void int float if else while do print")]
    assert "ID" not in types

def test_missing_semicolon():
    bad = "program p; var: int x main { x = 1 } end"
    try:
        parse(bad)
        assert False
    except UnexpectedInput:
        assert True

def test_precedence_mult_before_plus():
    tree = parse("program p; main { x = 1 + 2 * 3; } end")
    s = tree.pretty()
    assert "arith_expr" in s and "term" in s
