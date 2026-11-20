"""Small BLIF toolkit: parse, simulate (bit-parallel on Python ints), levels, LUT netlist writer.

No third-party code. Used by the generators and checks in this folder.
"""
import random


def _lines(path):
    buf = ""
    with open(path) as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].rstrip("\n").rstrip()
            if line.endswith("\\"):
                buf += line[:-1] + " "
                continue
            buf += line
            if buf.strip():
                yield buf.strip()
            buf = ""
    if buf.strip():
        yield buf.strip()


class Blif:
    def __init__(self):
        self.inputs, self.outputs = [], []
        self.nodes = {}          # name -> (fanins, rows, outval)
        self.order = []

    @staticmethod
    def read(path):
        b = Blif()
        cur = None
        for ln in _lines(path):
            if ln.startswith("."):
                tok = ln.split()
                cmd = tok[0]
                cur = None
                if cmd == ".inputs":
                    b.inputs += tok[1:]
                elif cmd == ".outputs":
                    b.outputs += tok[1:]
                elif cmd == ".names":
                    fan, out = tok[1:-1], tok[-1]
                    cur = [fan, [], None]
                    b.nodes[out] = cur
                elif cmd in (".model", ".end", ".default_input_arrival", ".default_output_required"):
                    pass
                else:
                    raise ValueError("unsupported " + cmd)
            else:
                tok = ln.split()
                if len(cur[0]) == 0:
                    cur[2] = tok[0]
                    cur[1].append("")
                else:
                    cur[1].append(tok[0])
                    cur[2] = tok[1]
        b._topo()
        return b

    def _topo(self):
        seen, order = set(self.inputs), []
        state = {}
        for root in list(self.nodes):
            if root in seen:
                continue
            stack = [(root, 0)]
            while stack:
                n, i = stack.pop()
                if n in seen:
                    continue
                fan = self.nodes[n][0]
                if i < len(fan):
                    stack.append((n, i + 1))
                    f = fan[i]
                    if f not in seen:
                        if f not in self.nodes:
                            raise ValueError("undriven " + f)
                        if state.get(f) == 1:
                            raise ValueError("cycle at " + f)
                        state[f] = 1
                        stack.append((f, 0))
                else:
                    seen.add(n)
                    state[n] = 2
                    order.append(n)
        self.order = order

    def simulate(self, values, width):
        """values: dict input -> int of `width` bits. Returns dict of all signals."""
        mask = (1 << width) - 1
        v = dict(values)
        for n in self.order:
            fan, rows, outv = self.nodes[n]
            acc = 0
            for r in rows:
                t = mask
                for ch, f in zip(r, fan):
                    if ch == "1":
                        t &= v[f]
                    elif ch == "0":
                        t &= ~v[f]
                    if not t:
                        break
                acc |= t
            if outv == "0":
                acc = ~acc
            v[n] = acc & mask
        return v

    def rename_ports(self, ref):
        """Rename primary inputs and outputs by position to those of `ref` (for netlists with nNN names)."""
        assert len(ref.inputs) == len(self.inputs) and len(ref.outputs) == len(self.outputs)
        m = dict(zip(self.inputs, ref.inputs))
        m.update(zip(self.outputs, ref.outputs))
        clash = set(m.values()) & (set(self.nodes) - set(m))
        assert not clash, clash
        nodes = {}
        for n, (fan, rows, outv) in self.nodes.items():
            nodes[m.get(n, n)] = ([m.get(f, f) for f in fan], rows, outv)
        self.nodes = nodes
        self.inputs = list(ref.inputs)
        self.outputs = list(ref.outputs)
        self._topo()
        return self

    def levels(self):
        lev = {i: 0 for i in self.inputs}
        for n in self.order:
            fan = self.nodes[n][0]
            lev[n] = 1 + max((lev[f] for f in fan), default=0) if fan else 0
        return lev

    def stats(self):
        lev = self.levels()
        return len(self.nodes), max(lev[o] for o in self.outputs)


def random_inputs(names, width, rng):
    return {n: rng.getrandbits(width) for n in names}


class LutNet:
    """Builder: add LUTs given fanins and a Python function of the fanin bits."""

    def __init__(self, inputs, k=6):
        self.inputs = list(inputs)
        self.k = k
        self.luts = {}       # name -> (fanins, truth table int)
        self.order = []
        self.lev = {i: 0 for i in self.inputs}

    def lut(self, name, fanins, fn):
        fanins = list(fanins)
        assert len(fanins) <= self.k, (name, len(fanins))
        assert name not in self.lev, name
        for f in fanins:
            assert f in self.lev, (name, f)
        tt = 0
        n = len(fanins)
        for m in range(1 << n):
            bits = [(m >> j) & 1 for j in range(n)]
            if fn(*bits) & 1:
                tt |= 1 << m
        self.luts[name] = (fanins, tt)
        self.order.append(name)
        self.lev[name] = 1 + max((self.lev[f] for f in fanins), default=0)
        return name

    def write(self, path, outputs, model="top"):
        live = set()
        stack = [o for o in outputs]
        while stack:
            s = stack.pop()
            if s in live or s in self.inputs:
                continue
            live.add(s)
            stack.extend(self.luts[s][0])
        with open(path, "w") as fh:
            fh.write(".model %s\n" % model)
            fh.write(".inputs " + " ".join(self.inputs) + "\n")
            fh.write(".outputs " + " ".join(outputs) + "\n")
            for name in self.order:
                if name not in live:
                    continue
                fan, tt = self.luts[name]
                n = len(fan)
                on = [m for m in range(1 << n) if (tt >> m) & 1]
                fh.write(".names " + " ".join(fan + [name]) + "\n")
                if not fan:
                    fh.write("1\n" if tt & 1 else "")
                    continue
                use_on = len(on) <= (1 << n) - len(on)
                rows = on if use_on else [m for m in range(1 << n) if not (tt >> m) & 1]
                for m in rows:
                    fh.write("".join(str((m >> j) & 1) for j in range(n)) + (" 1\n" if use_on else " 0\n"))
            fh.write(".end\n")
        return len(live), max(self.lev[o] for o in outputs)


def compare(ref, ours, width=2048, rounds=8, seed=1, extra=None):
    """Random-vector comparison by output name. extra: list of dict input->int vectors (width bits)."""
    rng = random.Random(seed)
    bad = 0
    total = 0
    batches = [random_inputs(ref.inputs, width, rng) for _ in range(rounds)]
    if extra:
        batches += extra
    for vals in batches:
        a = ref.simulate(vals, width)
        b = ours.simulate({k: vals[k] for k in ours.inputs}, width)
        for o in ref.outputs:
            if a[o] != b[o]:
                bad += 1
                break
        total += width
    return bad, total
