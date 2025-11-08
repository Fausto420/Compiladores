# demo_build.py
from parse_and_scan import parse, DEMO_CODE
from builder import build_symbols

fd = build_symbols(parse, DEMO_CODE)

print("GLOBALS")
for name, v in fd.globals._vars.items():
    print(name, ":", v.vtype)

print("\nFUNCTIONS")
for fname, fe in fd.funcs.items():
    print(f"* {fname} (VOID)")
    print("  params:", [(p.name, p.ptype) for p in fe.params])
    print("  locals:", [(n, e.vtype) for n, e in fe.vartable._vars.items() if not e.is_param])
