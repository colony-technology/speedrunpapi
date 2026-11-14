#!/usr/bin/env python3
"""Phase-state counts of the minimal Mealy machine (with final outputs) for a causal description.

usage: bvfsm.py states DESC.bv PHASEVEC one|zero [name=value ...]
    PHASEVEC one : the phase of a prefix is whether it contains a letter with PHASEVEC = 1 (a mark)
    PHASEVEC zero: ... a letter with PHASEVEC = 0 (the end of a mask of ones)
    name=value   : fixes scalar inputs (for example the rule)

Method (exact, no bounded exploration):
 1. The automaton of bvfsm (guessed scalars, no truncation guesses allowed) is explored forward from every
    start state; states that cannot reach an accepting end are removed (co-reachability).
 2. Subset construction over the remaining states gives a deterministic machine whose state after a prefix
    is the set of runs still able to finish. The description must be causal: on every letter the surviving
    runs emit one output, and at the end the accepting runs give one final output; this is checked.
 3. Moore refinement: two states are equivalent iff they are in the same phase, emit the same output on
    every letter, have successors that are equivalent, and agree on whether the word may end and on the
    final outputs. Letters with no continuation lead to a separate dead class.
 Validity here has the property Part 1 needs: the set of valid completions of a prefix depends only on
 its phase (and on how many letters it has, up to the length bound), so these classes are the Nerode
 classes over valid completions; the counts are those of the minimal machine.
"""
import itertools
import sys
from collections import deque

import bvfsm


def main(argv):
    path, pvec, pmode = argv[0], argv[1], argv[2]
    fixed = dict(a.split("=") for a in argv[3:])
    A, _ = bvfsm.make_pair(path, path)
    d = A.d
    if A.depth:
        raise SystemExit("states: the description truncates relative to the end of the word, so it is not causal")
    vnames = [nm for nm, _ in d.inputs_vec]
    pidx = vnames.index(pvec)
    snames = [nm for nm, _ in d.inputs_sc]
    free = [nm for nm in snames if nm not in fixed]
    if free:
        raise SystemExit("states: fix every scalar input (%s)" % ", ".join(free))
    sint = tuple(sorted((k, int(fixed[k])) for k in snames))
    letters = list(itertools.product((0, 1), repeat=len(vnames)))
    vout = [i for i, (_, n) in enumerate(d.outputs) if not n.scalar]
    # 1. forward graph over (pc, state)
    starts = [(0, s) for s in A.initial() if A.start_ok(s, dict(sint))]
    succ = {}
    q = deque(starts)
    seen = set(starts)
    import guard
    g = guard.Guard("states " + path)
    expanded = 0
    while q:
        node = q.popleft()
        expanded += 1
        g.tick(expanded, len(seen))
        pc, s = node
        edges = []
        for let in letters:
            for s2, o in A.step(s, let, sint, pc, None):
                n2 = (min(pc + 1, A.cap), s2)
                edges.append((let, tuple(o[i] for i in vout), n2))
                if n2 not in seen:
                    seen.add(n2)
                    q.append(n2)
        succ[node] = edges
    accept = {node for node in seen if node[0] >= d.lmin and A.end_ok(node[1])}
    pred = {node: [] for node in seen}
    for node, edges in succ.items():
        for _, _, n2 in edges:
            pred[n2].append(node)
    live = set(accept)
    q = deque(accept)
    while q:
        node = q.popleft()
        for p in pred[node]:
            if p not in live:
                live.add(p)
                q.append(p)
    # 2. subset construction
    start = frozenset(n for n in starts if n in live)
    sid = {start: 0}
    subsets = [start]
    phase = [0]
    trans = []      # per subset: dict letter -> (output, target id) for letters with a continuation
    finals = []     # per subset: None (may not end) or the final scalar outputs
    i = 0
    while i < len(subsets):
        S = subsets[i]
        tr = {}
        for let in letters:
            outs = set()
            T = set()
            for node in S:
                for l2, o, n2 in succ[node]:
                    if l2 == let and n2 in live:
                        outs.add(o)
                        T.add(n2)
            if not T:
                continue
            if len(outs) != 1:
                raise SystemExit("states: not causal: two outputs on one letter after a prefix")
            T = frozenset(T)
            if T not in sid:
                sid[T] = len(subsets)
                subsets.append(T)
                ph = phase[i] | int(let[pidx] == (1 if pmode == "one" else 0))
                phase.append(ph)
            else:
                ph = phase[i] | int(let[pidx] == (1 if pmode == "one" else 0))
                if phase[sid[T]] != ph:
                    raise SystemExit("states: one deterministic state reached in two phases")
            tr[let] = (outs.pop(), sid[T])
        trans.append(tr)
        fins = set(A.final(n[1], sint) for n in S if n in accept)
        if len(fins) > 1:
            raise SystemExit("states: not causal: two final outputs after one word")
        finals.append(fins.pop() if fins else None)
        i += 1
    # 3. Moore refinement
    cls = [(phase[k], finals[k], tuple(sorted((let, o) for let, (o, _) in trans[k].items()))) for k in range(len(subsets))]
    while True:
        names = {}
        lab = [names.setdefault(c, len(names)) for c in cls]
        cls2 = [(lab[k], tuple(sorted((let, lab[t]) for let, (_, t) in trans[k].items()))) for k in range(len(subsets))]
        n2 = len(set(cls2))
        if n2 == len(names):
            break
        cls = cls2
    counts = {}
    for k in range(len(subsets)):
        counts.setdefault(phase[k], set()).add(lab[k])
    before = len(counts.get(0, ()))
    after = len(counts.get(1, ()))
    print("states %s %s=%s fixed %s: deterministic states %d, minimal classes %d: before the phase change %d, after %d"
          % (path, pvec, pmode, " ".join("%s=%s" % kv for kv in sorted(fixed.items())), len(subsets),
             before + after, before, after))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
