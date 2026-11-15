<!-- opening -->

## The unit

Berkeley HardFloat Release 1 (Verilog), by John R. Hauser: `HardFloat-1.zip`, SHA-256 `6b3757c9fbfa2230c6a2b84605e39372cb589dd7500e979c4f0b8ecc8a03b14b`, from http://www.jhauser.us/arithmetic/HardFloat.html. It is not copied here; `replay.sh` takes the archive's path, checks its SHA-256 and unpacks it into `work/`.

Module certified: `roundRawFNToRecFN#(expWidth, sigWidth)`, options 0, RISCV specialization.

The claim and how each part of it was discharged: `certificate.md`. The proofs: `stage1.md` (exhaustive audit at small formats), `stage2.md` (the rounding datapath at every width), `stage3.md` (the exponent stage and the flags at every format, and the whole module at 135 formats).

## Files

| path | what |
| --- | --- |
| `certificate.md`, `stage1.md`, `stage2.md`, `stage3.md` | the certificate and its three parts |
| `replay.sh` | replays every check; argument: the path of `HardFloat-1.zip` |
| `stage1/ref.py` | the reference: exact rationals, IEEE 754-2019 rounding, recoded output |
| `stage1/harness.cpp`, `tb.v`, `one.sh`, `run_all.sh`, `table.py` | exhaustive comparison per format (Verilator) |
| `stage1/refcheck.py` | the reference against the host's binary16 and binary32 conversions |
| `stage1/tb_icarus.v`, `cross.sh` | Icarus against Verilator |
| `stage2/bvfsm.py`, `live.py`, `guard.py` | the tool: width-generic bit-vector descriptions, equality on every length, a shortest counterexample when there is one |
| `stage2/bv2v.py`, `emitcheck.py` | a description at one length emitted as Verilog; the emitter against the semantics |
| `stage2/hf_datapath.bv` | HardFloat's rounding datapath, lines 174–218 of `HardFloat_rawFN.v` |
| `stage2/ref_round.bv` | rounding at a marked position, from the definition |
| `stage2/hf_datapath_broken.bv`, `hf_datapath_broken2.bv`, `lemma_cu_c_rhs_broken.bv` | broken copies the tool must refute |
| `stage2/lemma_cu_c.bv`, `lemma_cu_c_lhs.bv`, `lemma_cu_c_rhs.bv` | lemma L1, HardFloat's tininess-after term |
| `stage2/check_ref.py`, `check_lemma.py` | the descriptions against the arithmetic definition |
| `stage2/run_equiv.sh` | the equivalence runs |
| `stage2/anchor/` | the description against HardFloat's internal signals in simulation |
| `stage2/formal/` | the description against HardFloat's netlist, Yosys SAT, p = 3…113 |
| `stage3/expstage.py` | the exponent stage and flags against IEEE 754, z3, symbolic in the format |
| `stage3/factcheck.py` | that model against HardFloat's outputs |
| `stage3/whole/` | the whole module against a module built from the proved formulas, Yosys SAT, 135 formats |
| `common/rounding.py` | rounding of an integer to a multiple of 2^r, the definition the checks compare with |
| `record/` | the logs of record and the SMT files |

## Commands

```
EDA_BIN=/path/to/oss-cad-suite/bin zsh replay.sh /path/to/HardFloat-1.zip
```

Tools used for the record: Python 3.15.2, Z3 5.3.3 (`Z3=` to choose the binary), Verilator 5.055 devel, Icarus Verilog 14.0 devel, Yosys 0.70+385. `HEAVY=` may name a command prefix for the long steps.

Single checks, after `replay.sh` has unpacked the archive:

```
python3 stage2/bvfsm.py equiv stage2/hf_datapath.bv stage2/ref_round.bv
HARDFLOAT=work/HardFloat-1 zsh stage2/formal/one.sh 53
python3 stage3/expstage.py stage3/smt
HARDFLOAT=work/HardFloat-1 zsh stage3/whole/one.sh 11 53
```
