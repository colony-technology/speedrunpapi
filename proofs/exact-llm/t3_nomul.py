"""The t3 kernel has no multiplier: the compiled object's disassembly, function by function, holds no multiply,
multiply-add or divide instruction, scalar or vector, integer or floating point.

usage: python t3_nomul.py [OBJECT]     (default: the kernel exact_llm.py builds and loads, t3-<hash>.dylib or .so)

Reads `objdump -d` (LLVM's or GNU's). Prints each function's instruction histogram and the whole object's; exit 1
if any function holds an instruction of the lists below. arm64 and x86-64 mnemonics; Apple's objdump writes a
vector arrangement into the mnemonic (mul.4s), GNU's into the operands, and both are read by the stem.
"""
import collections
import os
import re
import subprocess
import sys

ARM64_MUL = set("""mul madd msub mneg smull umull smulh umulh smaddl smsubl umaddl umsubl smnegl umnegl
    mla mls smull2 umull2 smlal smlal2 smlsl smlsl2 umlal umlal2 umlsl umlsl2 sqdmulh sqrdmulh sqdmull sqdmull2
    sqdmlal sqdmlal2 sqdmlsl sqdmlsl2 sqrdmlah sqrdmlsh pmul pmull pmull2 sdot udot usdot sudot smmla ummla usmmla
    fmul fmulx fmla fmls fnmul fmadd fmsub fnmadd fnmsub bfdot bfmmla bfmlalb bfmlalt fmmla""".split())
ARM64_DIV = {"sdiv", "udiv", "fdiv", "fsqrt", "frecpe", "frecps", "frsqrte", "frsqrts"}
X86_MUL = ("mul", "imul", "mulx", "pmul", "vpmul", "pmadd", "vpmadd", "vfmadd", "vfmsub", "vfnmadd", "vfnmsub",
           "vpdp", "mulss", "mulsd", "mulps", "mulpd", "vmul")
X86_DIV = ("div", "idiv", "divss", "divsd", "divps", "divpd", "vdiv", "sqrt", "vsqrt")
# RISC-V M extension (and its 64-bit word forms); on rv32i a C multiply becomes a call to a library routine instead
RISCV_MUL = {"mulh", "mulhsu", "mulhu", "mulw", "divu", "rem", "remu", "divw", "divuw", "remw", "remuw"}
LIBCALLS = ("__mul", "__div", "__udiv", "__mod", "__umod")


def stem(mnemonic):
    return mnemonic.split(".")[0].lower()


def flagged(m):
    s = stem(m)
    if s in ARM64_MUL or s in ARM64_DIV or s in RISCV_MUL:
        return True
    return s.startswith(X86_MUL) or s.startswith(X86_DIV)


def disassemble(path):
    tool = os.environ.get("OBJDUMP", "objdump")
    out = subprocess.run([tool, "-d", "-r", "--no-show-raw-insn", path], capture_output=True, text=True,
                         check=True).stdout
    calls = sorted(set(re.findall(r"\b(__(?:mul|div|udiv|mod|umod)\w*)", out)))
    if calls:
        raise SystemExit("library multiply or divide referenced: %s\nMULTIPLIER FOUND" % ", ".join(calls))
    funcs, name = collections.OrderedDict(), None
    for line in out.splitlines():
        m = re.match(r"^[0-9a-fA-F]+ <(.+)>:$", line.strip())
        if m:
            name = m.group(1)
            funcs.setdefault(name, collections.Counter())
            continue
        m = re.match(r"^\s*[0-9a-fA-F]+:\s+([a-z][a-z0-9.]*)", line)       # address, then the mnemonic
        if m and name is not None:
            funcs[name][m.group(1)] += 1
    return funcs


def main(argv):
    if len(argv) > 1:
        path = argv[1]
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import exact_llm as X
        path = X.t3_kernel().path
    funcs = disassemble(path)
    total, bad = collections.Counter(), []
    print("object %s" % path)
    for name, h in funcs.items():
        if not h:
            continue
        total.update(h)
        hits = sorted(m for m in h if flagged(m))
        bad += [(name, m, h[m]) for m in hits]
        print("%-22s %5d instructions; multiply or divide: %s" % (
            name, sum(h.values()), ", ".join("%s %d" % (m, h[m]) for m in hits) or "none"))
    print("histogram, all functions (%d instructions): %s" % (
        sum(total.values()), ", ".join("%s %d" % kv for kv in sorted(total.items(), key=lambda kv: (-kv[1], kv[0])))))
    print("multiply, multiply-add or divide instructions: %d%s" % (
        sum(n for _, _, n in bad), "" if not bad else " (" + "; ".join("%s in %s x%d" % (m, f, n) for f, m, n in bad) + ")"))
    print("NO MULTIPLIER" if not bad else "MULTIPLIER FOUND")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
