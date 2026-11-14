// Exhaustive comparison of the Verilated HardFloat roundRawFNToRecFN#(W, P) with the table ref.py wrote.
// Every input of the documented domain is applied:
//   control (tininess) 0/1; the six rounding modes 000 001 010 011 100 110; invalidExc, infiniteExc,
//   in_isNaN, in_isInf, in_isZero all 32 combinations; sign; every (W+2)-bit sExp; every (P+3)-bit sig.
// Finite nonzero inputs (all five special bits 0) are valid only when sig[P+2:P+1] != 00; the others are
// skipped and counted. For the special cases the documentation makes the other inputs irrelevant, so every
// value of them is applied and the output must be the documented one.
// usage: sim TABLE [DUMPFILE]   (DUMPFILE: core outputs, one line per valid finite nonzero input)
#include "Vtb.h"
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <vector>

static const int MODES[6] = {0, 1, 2, 3, 4, 6};
static const char *MODENAME[8] = {"near_even", "minMag", "min", "max", "near_maxMag", "?", "odd", "?"};

int main(int argc, char **argv) {
    const int W = TB_W, P = TB_P;
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("table"); return 2; }
    std::vector<unsigned char> tab;
    { unsigned char buf[1 << 16]; size_t n; while ((n = fread(buf, 1, sizeof buf, f)) > 0) tab.insert(tab.end(), buf, buf + n); }
    fclose(f);
    FILE *dump = argc > 2 ? fopen(argv[2], "w") : nullptr;
    const long nexp = 1L << (W + 2), nsig = 1L << (P + 3), sig0 = 1L << (P + 1);
    const long ncore = nexp * (nsig - sig0);
    if ((long)tab.size() != ncore * 5 * 9) { fprintf(stderr, "table size %zu, expected %ld\n", tab.size(), ncore * 45); return 2; }
    const int FB = P - 1;
    const uint32_t top3 = 7u << (W - 2), fmask = (1u << FB) - 1;
    const uint32_t nanv = (7u << (W - 2)) << FB | (1u << (P - 2)), nanc = (top3 << FB) | fmask;
    const uint32_t infv = (6u << (W - 2)) << FB, infc = top3 << FB;
    const uint32_t zerc = (top3 << FB) | fmask;
    Vtb *t = new Vtb;
    long applied = 0, skipped = 0, core = 0, bad = 0, badspecial = 0, badvalue = 0, badflags = 0;
    long both = 0, both_badvalue = 0, both_flags18 = 0;  // invalidExc = infiniteExc = 1: no caller drives this
    for (int ctl = 0; ctl < 2; ctl++)
    for (int mi = 0; mi < 6; mi++)
    for (int sp = 0; sp < 32; sp++)
    for (int sign = 0; sign < 2; sign++)
    for (long u = 0; u < nexp; u++)
    for (long sig = 0; sig < nsig; sig++) {
        const int mode = MODES[mi];
        const int inv = sp & 1, infx = sp >> 1 & 1, isnan = sp >> 2 & 1, isinf = sp >> 3 & 1, iszero = sp >> 4 & 1;
        // expected: sign bit, care and value of the rest, flags {invalid, infinite, overflow, underflow, inexact}
        int esign; uint32_t ecare, evalue; int eflags; bool special = true;
        if (inv)         { esign = 0;    ecare = nanc; evalue = nanv; eflags = 0x10; }
        else if (infx)   { esign = sign; ecare = infc; evalue = infv; eflags = 0x08; }
        else if (isnan)  { esign = 0;    ecare = nanc; evalue = nanv; eflags = 0; }
        else if (isinf)  { esign = sign; ecare = infc; evalue = infv; eflags = 0; }
        else if (iszero) { esign = sign; ecare = zerc; evalue = 0;    eflags = 0; }
        else {
            special = false;
            if (sig < sig0) { skipped++; continue; }
            int rule;
            switch (mode) {
                case 0: rule = 0; break;                     // ne
                case 4: rule = 1; break;                     // na
                case 1: rule = 2; break;                     // tz
                case 2: rule = sign ? 3 : 2; break;          // min: magnitude up when negative
                case 3: rule = sign ? 2 : 3; break;          // max: magnitude up when positive
                default: rule = 4; break;                    // odd
            }
            const long idx = ((u * (nsig - sig0) + (sig - sig0)) * 5 + rule) * 9;
            const unsigned char *r = &tab[idx];
            ecare = r[0] | r[1] << 8 | r[2] << 16 | (uint32_t)r[3] << 24;
            evalue = r[4] | r[5] << 8 | r[6] << 16 | (uint32_t)r[7] << 24;
            const int fl = r[8];
            const int uf = ctl ? (fl >> 2 & 1) : (fl >> 1 & 1);
            esign = sign;
            eflags = (fl >> 3 & 1) << 2 | uf << 1 | (fl & 1);
            core++;
        }
        t->control = ctl; t->invalidExc = inv; t->infiniteExc = infx;
        t->in_isNaN = isnan; t->in_isInf = isinf; t->in_isZero = iszero; t->in_sign = sign;
        t->in_sExp = (uint32_t)u; t->in_sig = (uint32_t)sig; t->roundingMode = mode;
        t->eval();
        applied++;
        const uint32_t out = t->out, gflags = t->exceptionFlags;
        const int gsign = out >> (W + P) & 1;
        const uint32_t grest = out & ((1u << (W + P)) - 1);
        const bool okv = gsign == esign && (grest & ecare) == (evalue & ecare);
        bool okf = (int)gflags == eflags;
        if (inv && infx) {             // value must be the NaN; flags are recorded, not judged
            both++;
            if (!okv) both_badvalue++;
            if (gflags == 0x18) both_flags18++;
            okf = true;
        }
        if (dump && !special)
            fprintf(dump, "%d %d %d %ld %ld %x %x\n", ctl, mode, sign, u, sig, out, gflags);
        if (!okv || !okf) {
            bad++;
            if (special) badspecial++;
            if (!okv) badvalue++;
            if (!okf) badflags++;
            if (bad <= 20) {
                const long sexp = u < (1L << (W + 1)) ? u : u - nexp;
                printf("MISMATCH w=%d p=%d tininess=%s mode=%s inv=%d inf=%d nan=%d isinf=%d zero=%d sign=%d sExp=%ld sig=0x%lx"
                       "  got out=0x%x flags=%02x  expected sign=%d value=0x%x care=0x%x flags=%02x\n",
                       W, P, ctl ? "after" : "before", MODENAME[mode], inv, infx, isnan, isinf, iszero, sign, sexp, sig,
                       out, gflags, esign, evalue, ecare, eflags);
            }
        }
    }
    printf("w=%d p=%d invalidExc&infiniteExc applied %ld value_wrong %ld flags_11000 %ld\n", W, P, both, both_badvalue, both_flags18);
    printf("w=%d p=%d applied %ld (finite nonzero %ld, special %ld) skipped_invalid_sig %ld mismatches %ld "
           "(special %ld, value %ld, flags %ld)\n",
           W, P, applied, core, applied - core, skipped, bad, badspecial, badvalue, badflags);
    if (dump) fclose(dump);
    delete t;
    return bad ? 1 : 0;
}
