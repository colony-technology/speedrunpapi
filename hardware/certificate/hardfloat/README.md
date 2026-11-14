<!-- opening -->

## The unit

Berkeley HardFloat Release 1 (Verilog), by John R. Hauser: `HardFloat-1.zip`, SHA-256 `6b3757c9fbfa2230c6a2b84605e39372cb589dd7500e979c4f0b8ecc8a03b14b`, from http://www.jhauser.us/arithmetic/HardFloat.html. It is not copied here; `replay.sh` takes the archive's path, checks its SHA-256 and unpacks it into `work/`.

Module certified: `roundRawFNToRecFN#(expWidth, sigWidth)`, options 0, RISCV specialization.

## Files

| path | what |
| --- | --- |
| `replay.sh` | replays every check; argument: the path of `HardFloat-1.zip` |
| `stage1/ref.py` | the reference: exact rationals, IEEE 754-2019 rounding, recoded output |
| `stage1/harness.cpp`, `tb.v`, `one.sh`, `run_all.sh`, `table.py` | exhaustive comparison per format (Verilator) |
| `stage1/refcheck.py` | the reference against the host's binary16 and binary32 conversions |
| `stage1/tb_icarus.v`, `cross.sh` | Icarus against Verilator |
| `stage2/bvfsm.py`, `live.py`, `guard.py`, `states.py` | the tool: width-generic bit-vector descriptions, equality on every length, phase-state counts |
| `stage2/bv2v.py`, `emitcheck.py` | a description at one length emitted as Verilog; the emitter against the semantics |
| `stage2/hf_datapath.bv` | HardFloat's rounding datapath, lines 174–218 of `HardFloat_rawFN.v` |
| `stage2/ref_round.bv` | rounding at a marked position, from the definition |
| `stage2/hf_datapath_broken*.bv`, `lemma_cu_c_rhs_broken.bv` | broken copies the tool must refute |
| `stage2/lemma_cu_c*.bv` | lemma L1, HardFloat's tininess-after term (`lemma_cu*.bv`: the first, non-causal form) |
| `stage2/round_mark.bv`, `design1c.bv` (`design1.bv`) | the machine contracts counted for the cut-off theorem |
| `stage2/check_*.py` | each description against the arithmetic definition |
| `stage2/anchor/` | the description against HardFloat's internal signals in simulation |
| `stage2/formal/` | the description against HardFloat's netlist, Yosys SAT, p = 3…113 |
| `stage2/run_equiv.sh`, `run_states.sh`, `run_lemma.sh` | the stage 2 runs |
| `stage3/expstage.py` | the exponent stage and flags against IEEE, z3, symbolic in the format |
| `stage3/factcheck.py` | that model against HardFloat's outputs |
| `common/round_states.py` | rounding at a marked position and its state counts (the measured anchor) |
| `record/` | the logs of record and the SMT files |

## Commands

```
EDA_BIN=/path/to/oss-cad-suite/bin zsh replay.sh /path/to/HardFloat-1.zip
```

Tools used for the record: Python 3.15.2, Z3 5.3.3 (`Z3=` to choose the binary), Verilator 5.055 devel, Icarus Verilog 14.0 devel, Yosys 0.70+385. `HEAVY=` may name a command prefix for the long steps. A full replay takes about 30 minutes on an Apple M1 mini.

Single checks:

```
python3 stage2/bvfsm.py equiv stage2/hf_datapath.bv stage2/ref_round.bv
python3 stage2/bvfsm.py states stage2/design1c.bv mark one ne=1 na=0 tz=0 aw=0 odd=0
HARDFLOAT=work/HardFloat-1 zsh stage2/formal/one.sh 53
python3 stage3/expstage.py stage3/smt
```
