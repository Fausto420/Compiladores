from lark.exceptions import UnexpectedInput
from parse_and_scan import parse, scan

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

def test_demo_parses():
    tree = parse(DEMO)
    assert tree is not None

def test_keywords_not_ids():
    kw = "programa inicio fin vars nula entero flotante si sino mientras haz escribe"
    types = [t[0] for t in scan(kw)]
    assert "ID" not in types

def test_missing_semicolon():
    bad = "programa p; vars: x: entero; inicio { x = 1 } fin"
    try:
        parse(bad)
        assert False, "Debió fallar por ; faltante"
    except UnexpectedInput:
        assert True

def test_precedence_mult_before_plus():
    tree = parse("programa p; vars: x: entero; inicio { x = 1 + 2 * 3; } fin")
    s = tree.pretty()
    assert "exp_simple" in s and "termino" in s