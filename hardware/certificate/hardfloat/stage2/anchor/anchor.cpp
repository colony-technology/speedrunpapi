// Dumps HardFloat's internal datapath signals (lines 174-218) for every valid finite nonzero input of
// roundRawFNToRecFN#(TB_W, TB_P), one line per distinct (roundMask, adjustedSig, mode, sign):
//   mask sig mode sign roundedSig roundPosBit anyRoundExtra        (decimal)
#include "Vtb.h"
#include "Vtb___024root.h"
#include <cstdio>
#include <cstdint>
#include <set>
#include <tuple>

int main() {
    const int W = TB_W, P = TB_P;
    static const int MODES[6] = {0, 1, 2, 3, 4, 6};
    Vtb *t = new Vtb;
    std::set<std::tuple<uint32_t, uint32_t, int, int>> seen;
    for (int mi = 0; mi < 6; mi++)
    for (int sign = 0; sign < 2; sign++)
    for (uint32_t u = 0; u < (1u << (W + 2)); u++)
    for (uint32_t sig = 1u << (P + 1); sig < (1u << (P + 3)); sig++) {
        t->control = 1; t->invalidExc = 0; t->infiniteExc = 0; t->in_isNaN = 0; t->in_isInf = 0; t->in_isZero = 0;
        t->in_sign = sign; t->in_sExp = u; t->in_sig = sig; t->roundingMode = MODES[mi];
        t->eval();
        auto *r = t->rootp;
        uint32_t mask = r->tb__DOT__dut__DOT__roundAnyRawFNToRecFN__DOT__genblk2__DOT__roundMask;
        auto key = std::make_tuple(mask, sig, MODES[mi], sign);
        if (!seen.insert(key).second) continue;
        printf("%u %u %d %d %u %u %u\n", mask, sig, MODES[mi], sign,
               (uint32_t)r->tb__DOT__dut__DOT__roundAnyRawFNToRecFN__DOT__genblk2__DOT__roundedSig,
               (uint32_t)r->tb__DOT__dut__DOT__roundAnyRawFNToRecFN__DOT__genblk2__DOT__roundPosBit,
               (uint32_t)r->tb__DOT__dut__DOT__roundAnyRawFNToRecFN__DOT__genblk2__DOT__anyRoundExtra);
    }
    delete t;
    return 0;
}
