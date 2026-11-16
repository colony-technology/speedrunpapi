## By type, per token (SmolLM2-135M, route f64)

| per token | exact-16, last position (context 64) | with the checks | added | exact-16, prefill average | with the checks | added |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| steps: multiply-adds in the matrix products | 138,206,976 | 138,885,964 | 678,988 | 138,206,976 | 138,885,964 | 678,988 |
| steps: multiply-adds elsewhere | 207,936 | 334,656 | 126,720 | 207,936 | 334,656 | 126,720 |
| **steps, total** | **138,414,912** | **139,220,620** | **805,708 (+0.58%)** | **138,414,912** | **139,220,620** | **805,708 (+0.58%)** |
| apart: adds and subtractions | 277,144 | 2,043,275 | 1,766,131 | 277,144 | 2,031,935 | 1,754,791 |
| apart: multiplies by a constant (shifts left by a fixed amount, negation) | 231,552 | 434,304 | 202,752 | 231,552 | 434,304 | 202,752 |
| apart: other multiplies (norm weight, SiLU(gate) times up) | 81,216 | 186,292 | 105,076 | 81,216 | 186,292 | 105,076 |
| **apart, total** | **589,912** | **2,663,871** | **2,073,959 (+351.57%)** | **589,912** | **2,652,531** | **2,062,619 (+349.65%)** |
| looks: roundings, rescales and splits | 976,128 | 1,632,196 | 656,068 | 976,128 | 1,632,196 | 656,068 |
| looks: clamps | 370,395 | 728,667 | 358,272 | 370,395 | 728,667 | 358,272 |
| looks: comparisons | 581,376 | 1,697,857 | 1,116,481 | 532,992 | 1,649,473 | 1,116,481 |
| looks: bit lengths | 542 | 542 |  | 542 | 542 |  |
| looks: divisions | 52,477 | 52,477 |  | 52,477 | 52,477 |  |
| looks: square roots | 61 | 61 |  | 61 | 61 |  |
| looks: table reads | 127,421 | 254,205 | 126,784 | 127,421 | 254,205 | 126,784 |
| **looks, total** | **2,108,400** | **4,366,005** | **2,257,605 (+107.08%)** | **2,060,016** | **4,317,621** | **2,257,605 (+109.59%)** |
| not counted: selects by a mask | 127,208 | 236,648 | 109,440 | 127,208 | 236,648 | 109,440 |
| not counted: data movement (concatenate, gather and scatter) | 664 | 905 | 241 | 484.94 | 486.83 | 1.89 |
| not counted: run-time checks (asserts) | 955,417 | 587,590 | -367,827 | 955,417 | 587,590 | -367,827 |
| not counted: instrumentation (clamp counters, peaks, held p) | 1,053,409 | 1,053,409 |  | 1,053,409 | 1,053,409 |  |
| not counted: inside another count | 1,641,634 | 5,950,782 | 4,309,148 | 1,641,634 | 5,950,782 | 4,309,148 |
| **steps per look** | **65.6** | **31.9** | | **67.2** | **32.2** | |

## What the checks add, by site (last position, context 64)

| category: site | added per token |
| --- | ---: |
| adds and subtractions: brackets: rounding | 930,048 |
| adds and subtractions: spare rows: product outputs, the two sums | 204,672 |
| adds and subtractions: input sums: formed again by the product that reads the vector (a row of ones) | 185,951 |
| adds and subtractions: SiLU table | 138,240 |
| adds and subtractions: input sums: made where the vector is made | 133,661 |
| adds and subtractions: brackets: division | 52,477 |
| adds and subtractions: spare rows: scores and context outputs, the two sums | 51,840 |
| adds and subtractions: exp table | 34,560 |
| adds and subtractions: spare rows: the two sums of the keys, kept beside the cache | 17,280 |
| adds and subtractions: spare rows: the two sums of each v, as it enters the cache | 11,520 |
| adds and subtractions: v split put together | 5,760 |
| adds and subtractions: brackets: square root | 122 |
| bit lengths: norm: bit length of the largest |x| | 61 |
| bit lengths: norm | -61 |
| clamps: clamp: residual, gate, up | 127,296 |
| clamps: clamp: prepare | 98,496 |
| clamps: SiLU table | 46,080 |
| clamps: exp table | 34,560 |
| clamps: clamp: q | 17,280 |
| clamps: attention: softmax | 17,280 |
| clamps: clamp: k, v as they enter the cache | 11,520 |
| clamps: v split put together | 5,760 |
| comparisons: brackets: rounding | 465,024 |
| comparisons: made twice: compare (clamp) | 254,592 |
| comparisons: SiLU table | 138,240 |
| comparisons: peel: the two largest |x| | 98,496 |
| comparisons: brackets: division | 52,477 |
| comparisons: made twice: compare (silu) | 46,080 |
| comparisons: made twice: compare (attention) | 17,550 |
| comparisons: made twice: compare (exp) | 17,280 |
| comparisons: attention: softmax | 17,280 |
| comparisons: v split put together | 5,760 |
| comparisons: spare rows: compare | 2,042 |
| comparisons: input sums: compare | 751 |
| comparisons: brackets: bit length | 542 |
| comparisons: made twice: compare (peel_index) | 242 |
| comparisons: made twice: compare (rope_tables) | 64 |
| comparisons: brackets: square root | 61 |
| data movement (concatenate, gather and scatter): prepare | 121 |
| data movement (concatenate, gather and scatter): forward | 120 |
| inside another count: brackets: rounding | 2,326,563 |
| inside another count: made twice: compare (clamp) | 763,776 |
| inside another count: brackets: division | 209,908 |
| inside another count: spare rows: product outputs, the two sums | 204,672 |
| inside another count: peel: the two largest |x| | 196,992 |
| inside another count: made twice: compare (silu) | 138,240 |
| inside another count: spare rows: q . key sums, p . v sums | 103,680 |
| inside another count: SiLU table | 92,160 |
| inside another count: made twice: compare (attention) | 52,650 |
| inside another count: checks: fdiv | 52,477 |
| inside another count: made twice: compare (exp) | 51,840 |
| inside another count: spare rows: scores and context outputs, the two sums | 51,840 |
| inside another count: exp table | 17,280 |
| inside another count: checks: compare (cache_entry) | 11,520 |
| inside another count: spare rows: the two sums of each v, as it enters the cache | 11,520 |
| inside another count: v split put together | 5,760 |
| inside another count: spare rows: the two sums of the keys, kept beside the cache | 5,760 |
| inside another count: brackets: bit length | 3,130 |
| inside another count: spare rows: compare | 3,063 |
| inside another count: input sums: compare | 2,253 |
| inside another count: spare rows: product inputs . c1, c2 | 1,266 |
| inside another count: checks: attention | 810 |
| inside another count: made twice: compare (peel_index) | 726 |
| inside another count: product: peeled terms, 2^sh | 432 |
| inside another count: brackets: square root | 244 |
| inside another count: checks: product | 211 |
| inside another count: made twice: compare (rope_tables) | 192 |
| inside another count: norm: bit length of the largest |x| | 122 |
| inside another count: checks: isqrt | 61 |
| multiplies by a constant (shifts left by a fixed amount, negation): peel: the two largest |x| | 196,992 |
| multiplies by a constant (shifts left by a fixed amount, negation): v split put together | 5,760 |
| multiply-adds elsewhere: SiLU table | 92,160 |
| multiply-adds elsewhere: exp table | 34,560 |
| multiply-adds in the matrix products: spare rows: product inputs . c1, c2 | 301,516 |
| multiply-adds in the matrix products: spare rows: product outputs, the two sums | 204,672 |
| multiply-adds in the matrix products: spare rows: q . key sums, p . v sums | 103,680 |
| multiply-adds in the matrix products: spare rows: scores and context outputs, the two sums | 51,840 |
| multiply-adds in the matrix products: spare rows: the two sums of each v, as it enters the cache | 11,520 |
| multiply-adds in the matrix products: spare rows: the two sums of the keys, kept beside the cache | 5,760 |
| other multiplies (norm weight, SiLU(gate) times up): brackets: division | 104,954 |
| other multiplies (norm weight, SiLU(gate) times up): brackets: square root | 122 |
| roundings, rescales and splits: brackets: rounding | 465,024 |
| roundings, rescales and splits: SiLU table | 138,240 |
| roundings, rescales and splits: exp table | 51,840 |
| roundings, rescales and splits: brackets: bit length | 481 |
| roundings, rescales and splits: spare rows: product inputs . c1, c2 | 422 |
| roundings, rescales and splits: norm: bit length of the largest |x| | 61 |
| run-time checks (asserts): norm: integer square root | -488 |
| run-time checks (asserts): fdiv: softmax p | -120,960 |
| run-time checks (asserts): fdiv: norm: mean square, x / r | -246,379 |
| selects by a mask: SiLU table | 92,160 |
| selects by a mask: attention: softmax | 17,280 |
| table reads: SiLU table | 92,160 |
| table reads: exp table | 34,560 |
| table reads: rotary | 64 |

## Decode step: fixed and per key read

| per token, decode step | exact-16, fixed | per key read | with the checks, fixed | per key read |
| --- | ---: | ---: | ---: | ---: |
| steps | 135,062,592 | 52,380 | 135,747,340 | 54,270 |
| apart | 486,232 | 1,620 | 2,387,391 | 4,320 |
| looks | 1,866,480 | 3,780 | 3,882,165 | 7,560 |
