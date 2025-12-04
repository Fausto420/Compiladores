from lark.exceptions import UnexpectedInput
from parse_and_scan import parse, scan

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