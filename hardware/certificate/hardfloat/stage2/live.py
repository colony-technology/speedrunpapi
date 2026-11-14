#!/usr/bin/env python3
"""Live states of one description's automaton: reachable from a start and able to reach an accepting end.
bvfsm.product_search expands only pairs of live states (a dead state accepts no word, so this removes no
counterexample). States are interned to integers to keep the sets compact; the search stops with
guard.Stop when the state cap or the memory limit is reached. usage (diagnostic): live.py DESC.bv"""
import itertools
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bvfsm  # noqa: E402
import guard  # noqa: E402


def live_states(A, snames, depth, cap, lmin, g=None):
    """Returns (set of live node keys (pc, rem, state, sint), number reached)."""
    g = g or guard.Guard("live " + A.d.path)
    d = A.d
    vnames = [nm for nm, _ in d.inputs_vec]
    letters = list(itertools.product((0, 1), repeat=len(vnames)))
    own = [nm for nm, _ in d.inputs_sc]
    ids = {}
    nodes = []

    def nid(node):
        i = ids.get(node)
        if i is None:
            i = len(nodes)
            ids[node] = i
            nodes.append(node)
        return i

    q = deque()
    for sv in itertools.product((0, 1), repeat=len(own)):
        sint = tuple(sorted(zip(own, sv)))
        for s in A.initial():
            if A.start_ok(s, dict(sint)):
                node = (0, None, s, sint)
                if node not in ids:
                    q.append(nid(node))
    pred = {}
    accept = []
    expanded = 0
    while q:
        i = q.popleft()
        pc, rem, s, sint = nodes[i]
        expanded += 1
        g.tick(expanded, len(nodes))
        rems = [rem] if rem is not None else ([None, depth] if depth > 0 else [None])
        for r in rems:
            for let in letters:
                for s2, _ in A.step(s, let, sint, pc, r):
                    nrem = None if r is None else r - 1
                    node2 = (min(pc + 1, cap), nrem, s2, sint)
                    new = node2 not in ids
                    j = nid(node2)
                    pred.setdefault(j, []).append(i)
                    if new:
                        if (nrem == 0 or depth == 0) and node2[0] >= lmin and A.end_ok(s2):
                            accept.append(j)
                        if nrem != 0:
                            q.append(j)
        A.trim()
    live = set(accept)
    q = deque(accept)
    while q:
        j = q.popleft()
        for i in pred.get(j, ()):
            if i not in live:
                live.add(i)
                q.append(i)
    n = len(nodes)
    out = {nodes[i] for i in live}
    del pred, ids, nodes
    return out, n


def main():
    A, _ = bvfsm.make_pair(sys.argv[1], sys.argv[1])
    try:
        live, n = live_states(A, None, A.depth, A.cap, A.d.lmin)
    except guard.Stop as e:
        print(e)
        return 3
    print("%s: reachable %d, live %d" % (sys.argv[1], n, len(live)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
