#!/usr/bin/env python3
"""Stage 3: HardFloat's exponent stage and flags against the IEEE definitions, for every format at once.

Integer model, symbolic in the format. Variables:
    H >= 2         2^(w-2), so 2^(w-1) = B = 2H and w >= 3; z3 proves the claims for every integer H >= 2,
                   powers of two among them
    p              3 <= p <= H + 3 (HardFloat doc section 2: p <= 2^(w-2) + 3)
    sExp           -4B <= sExp <= 4B - 1 (doc 5.3: w+2 bits)
    d              doShiftSigDown1 = in_sig[p+2] (the top 1-bit is at m = p+1+d; doc 5.3: top bits not 00)
    rule           one of ne na tz aw odd (mode and sign, doc 6.2); after (control: tininess after rounding)
Word coordinates: bit 0 of in_sig is position 0, T = p+3 the word length, m = p+1+d the top 1-bit.
x = in_sig * 2^lambda with lambda = sExp - 2B - p - 1 (doc 5.2, 5.3), so
    E = position of 2^emin = B + p + 3 - sExp     (emin = 2 - B)
    O = position of 2^(emax+1) = 3B + p + 1 - sExp  (emax = B - 1)
    S = E - p + 1 (quantum of the subnormals), Ru = m - p + 1 = 2 + d (quantum at precision p)
    R* = max(Ru, S), the IEEE rounding position.

HardFloat, transcribed from source/HardFloat_rawFN.v (options 0, inExpWidth = outExpWidth, RISCV):
    lowMaskLoHi (primitives line 85, used at line 179): roundMask_main[j] = [u + j < B + 2], j = 0..p, with
        u = sExp[w:0] read unsigned (sExp mod 4B); so its number of ones is k = clamp(B + 2 - u, 0, p + 1)
    roundMask = {roundMask_main | d, 2'b11} (line 188): ones below RHF = 2 + max(d, k)
    t = roundedSig >> p (line 221) = bits T-1 and T of y = rho(x, RHF)   (roundedSig[i] = y[i+2])
    sRoundedExp = sExp + t
    common_overflow = sRoundedExp >>> (w-1) >= 3   (line 228)  <=>  sExp + t >= 3B
    common_totalUnderflow = sRoundedExp < outMinNonzeroExp = B + 3 - p   (line 230)
    common_underflow (line 244): totalUnderflow | (anyRound & (sExp >>> w <= 0, i.e. sExp < 2B)
        & roundMask[2+d] & ~(after & ~roundMask[3+d] & roundCarry & roundPosBit & unboundedRange_roundIncr))
        roundMask[j] = [j < RHF]; roundCarry = bit m+1 of y (line 241); roundPosBit = bit RHF-1 of x
    common_inexact = totalUnderflow | anyRound (line 259); inexact = overflow | common_inexact (268)
    result (lines 271-312): overflow -> infinity if ne|na|magUp else the largest finite number;
        totalUnderflow -> the smallest subnormal if magUp|odd else zero; otherwise exponent field
        sRoundedExp and the fraction bits of y.
The datapath is abstracted by facts about rho(x, r) that hold for every word (stage 2 proves that HardFloat's
roundedSig, roundPosBit, anyRoundExtra are rho, bit r-1 and sticky for every width):
    i_r inexact at r; for r <= m: the top bit of y is m + c_r (c_r: carried to 2^(m+1)), y = x if not i_r;
    for r > m: y is 0 or 2^r (z_r), always inexact; r >= m+2: y = 2^r exactly for aw and odd;
    r = m+1: tz gives 0, aw and odd give 2^r; tz and odd never carry; equal positions, equal facts;
    i is monotone in r. Lemma L1 (stage 2 tool, lemma_cu.bv, every width): if RHF = Ru + 1 then
    c_Ru <=> roundPosBit & roundCarry & unboundedRange_roundIncr.
Reference (IEEE 754-2019 as in stage 1's ref.py), in the same coordinates:
    y* = rho(x, R*); overflow <=> R* <= m & m + c_R* >= O   (y* > Omega, see stage3.md)
    tiny before <=> m < E; tiny after <=> m + c_Ru < E; inexact = overflow | i_R*; underflow = tiny & inexact.
Each claim is checked by asking z3 for a model of (domain, facts, not claim): "unsat" proves the claim.
usage: expstage.py OUTDIR    (writes OUTDIR/*.smt2 and prints the results)
"""
import os
import subprocess
import sys

Z3 = os.environ.get("Z3", "z3")

DECLS = """
(declare-const H Int) (declare-const p Int) (declare-const sExp Int) (declare-const d Int)
(declare-const ne Bool) (declare-const na Bool) (declare-const tz Bool) (declare-const aw Bool) (declare-const odd Bool)
(declare-const after Bool)
(declare-const rpb Bool) (declare-const unbIncr Bool)
"""

# rounding positions abstracted: HF (RHF), IEEE (RS), unbounded (RU)
POS = ("HF", "S", "U")


def body(variant):
    L = [DECLS]
    for r in POS:
        L.append("(declare-const i%s Bool) (declare-const c%s Bool) (declare-const z%s Bool)" % (r, r, r))
    A = L.append
    A("(define-fun B () Int (* 2 H))")
    A("(define-fun T () Int (+ p 3))")
    A("(define-fun m () Int (+ p 1 d))")
    A("(define-fun E () Int (- (+ B p 3) sExp))")
    A("(define-fun O () Int (- (+ (* 3 B) p 1) sExp))")
    A("(define-fun Sq () Int (- (+ B 4) sExp))")
    A("(define-fun Ru () Int (+ 2 d))")
    A("(define-fun RS () Int (ite (>= Ru Sq) Ru Sq))")
    A("(define-fun u () Int (ite (>= sExp 0) sExp (+ sExp (* 4 B))))")
    A("(define-fun k0 () Int (- (+ B 2) u))")
    A("(define-fun k () Int (ite (< k0 0) 0 (ite (> k0 (+ p 1)) (+ p 1) k0)))")
    A("(define-fun RHF () Int (+ 2 (ite (>= d k) d k)))")
    A("(define-fun RU () Int Ru)")
    # domain
    A("(assert (>= H 2)) (assert (>= p 3)) (assert (<= p (+ H 3))) (assert (or (= d 0) (= d 1)))")
    A("(assert (<= (- (* 4 B)) sExp)) (assert (<= sExp (- (* 4 B) 1)))")
    A("(assert (= 1 (+ (ite ne 1 0) (ite na 1 0) (ite tz 1 0) (ite aw 1 0) (ite odd 1 0))))")
    # facts about rho at each abstracted position
    for r, R in (("HF", "RHF"), ("S", "RS"), ("U", "RU")):
        A("(assert (=> (> %s m) i%s))" % (R, r))
        A("(assert (=> (and (<= %s m) (not i%s)) (not c%s)))" % (R, r, r))
        A("(assert (=> (and (<= %s m) (or tz odd)) (not c%s)))" % (R, r))
        A("(assert (=> (>= %s (+ m 2)) (= z%s (or aw odd))))" % (R, r))
        A("(assert (=> (= %s (+ m 1)) (and (=> tz (not z%s)) (=> (or aw odd) z%s))))" % (R, r, r))
    for a, Ra in (("HF", "RHF"), ("S", "RS"), ("U", "RU")):
        for b, Rb in (("HF", "RHF"), ("S", "RS"), ("U", "RU")):
            if a < b:
                A("(assert (=> (= %s %s) (and (= i%s i%s) (= c%s c%s) (= z%s z%s))))" % (Ra, Rb, a, b, a, b, a, b))
            if a != b:
                A("(assert (=> (and (<= %s %s) i%s) i%s))" % (Ra, Rb, a, b))
    # HardFloat
    A("(define-fun carryHF () Bool (ite (<= RHF m) cHF zHF))")              # bit m+1 of y
    A("(define-fun t () Int (ite (<= RHF m) (+ d (ite cHF 1 0)) (ite (= RHF T) (ite zHF 2 0) (ite zHF 1 0))))")
    A("(define-fun sRE () Int (+ sExp t))")
    ovf = "(>= sRE (* 3 B))" if variant != "mut_ovf" else "(>= sRE (- (* 3 B) 1))"
    tu = "(< sRE (- (+ B 3) p))" if variant != "mut_tu" else "(<= sRE (- (+ B 3) p))"
    A("(define-fun ovfHF () Bool %s)" % ovf)
    A("(define-fun tuHF () Bool %s)" % tu)
    A("(define-fun tiny2 () Bool (> RHF (+ Ru 1)))")
    A("(define-fun tiny1 () Bool (> RHF Ru))")
    A(("(define-fun ufHF () Bool (or tuHF (and iHF (< sExp B2) tiny1 (not (and after (not tiny2) carryHF rpb unbIncr)))))" if variant != "mut_uf" else "(define-fun ufHF () Bool (or tuHF (and iHF (< sExp B2) tiny1)))")
      .replace("B2", "(* 2 B)"))
    A("(define-fun ixHF () Bool (or ovfHF tuHF iHF))")
    # Lemma L1
    A("(assert (=> (= RHF (+ Ru 1)) (= cU (and rpb carryHF unbIncr))))")
    # reference
    A("(define-fun ovfR () Bool (and (<= RS m) (>= (+ m (ite cS 1 0)) O)))")
    A("(define-fun ixR () Bool (or ovfR iS))")
    A("(define-fun tinyR () Bool (ite after (< (+ m (ite cU 1 0)) E) (< m E)))")
    A("(define-fun ufR () Bool (and tinyR ixR))")
    # results: kind 0 zero, 1 finite, 2 infinity, 3 largest finite; finite: exponent field, fraction tag
    #   tag 0: a power of two (fraction 0); tag 1: the bits of rho(x, r) below its top, with r = the position
    A("(define-fun kHF () Int (ite ovfHF (ite (or ne na aw) 2 3) (ite tuHF (ite (or aw odd) 1 0) 1)))")
    A("(define-fun eHF () Int (ite tuHF (- (+ B 3) p) sRE))")
    A("(define-fun pow2HF () Bool (or tuHF (ite (<= RHF m) cHF zHF)))")
    A("(define-fun kR () Int (ite ovfR (ite (or ne na aw) 2 3) (ite (and (> RS m) (not zS)) 0 1)))")
    A("(define-fun topR () Int (ite (<= RS m) (+ m (ite cS 1 0)) RS))")
    A("(define-fun eR () Int (+ (- sExp p 1) topR))")
    A("(define-fun pow2R () Bool (ite (<= RS m) cS zS))")
    claims = {
        "overflow": "(= ovfHF ovfR)",
        "inexact": "(= ixHF ixR)",
        "underflow": "(= ufHF ufR)",
        "kind": "(= kHF kR)",
        "finite_value": "(=> (and (= kHF 1) (= kR 1)) (and (= eHF eR) (= pow2HF pow2R) (or pow2HF (= RHF RS))))",
        "exponent_field_code": "(=> (= kHF 1) (and (<= H eHF) (< eHF (* 6 H))))",
        "sRoundedExp_fits_w+3_bits": "(and (<= (- (* 8 B)) sRE) (< sRE (* 8 B)))",
        "lowMask_reads_inside_c": "(<= (+ (- (+ B 2) p) p 1) (* 4 B))",
        "sExp_lt_2B_term_redundant": "(= ufHF (or tuHF (and iHF tiny1 (not (and after (not tiny2) carryHF rpb unbIncr)))))",
    }
    return "\n".join(L), claims


def run(path):
    out = subprocess.run([Z3, "-T:600", path], capture_output=True, text=True).stdout.strip()
    return out.splitlines()[0] if out else "?"


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    print(subprocess.run([Z3, "--version"], capture_output=True, text=True).stdout.strip())
    bad = 0
    for variant in ("hardfloat", "mut_tu", "mut_ovf", "mut_uf"):
        base, claims = body(variant)
        # the domain and facts are satisfiable (the claims are not vacuous)
        f = os.path.join(outdir, "%s_domain.smt2" % variant)
        open(f, "w").write(base + "\n(check-sat)\n")
        print("%-10s domain and facts: %s" % (variant, run(f)))
        for name, c in claims.items():
            f = os.path.join(outdir, "%s_%s.smt2" % (variant, name))
            open(f, "w").write(base + "\n(assert (not %s))\n(check-sat)\n(get-model)\n" % c)
            r = run(f)
            verdict = "proved" if r == "unsat" else ("COUNTERMODEL" if r == "sat" else r)
            print("%-10s %-28s %s -> %s" % (variant, name, r, verdict))
            if variant == "hardfloat" and r != "unsat":
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
