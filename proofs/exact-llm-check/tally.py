"""Totals over the batches of a run.py output file (times, tokens, counters), one JSON line per batch and one total.

    python3 tally.py retime.jsonl
"""
import json
import sys

R = [json.loads(l) for l in open(sys.argv[1])]
keys = [("plain", "run_s"), ("trace", "trace_run_s"), ("trace", "trace_bytes"),
        ("check_freivalds", "check_s"), ("check_freivalds", "prep_s"), ("check_freivalds", "loop_s"),
        ("check_direct", "check_s"), ("check_direct", "prep_s"), ("check_direct", "loop_s"),
        ("check_freivalds", "tokens"), ("check_freivalds", "check_macs"), ("check_freivalds", "elem_ops"),
        ("check_direct", "check_macs"), ("check_freivalds", "freivalds_checks")]
tot = {}
for r in R:
    row = {"batch": r["batch"], "fv": r["check_freivalds"]["verdict"], "dir": r["check_direct"]["verdict"]}
    for a, b in keys:
        v = r[a].get(b)
        row["%s.%s" % (a, b)] = round(v, 2) if isinstance(v, float) else v
        tot["%s.%s" % (a, b)] = tot.get("%s.%s" % (a, b), 0) + (v or 0)
    print(json.dumps(row))
print(json.dumps({"total": {k: round(v, 2) if isinstance(v, float) else v for k, v in tot.items()},
                  "all_accept": all(r["check_freivalds"]["verdict"] == "accept" and r["check_direct"]["verdict"] == "accept" for r in R)}))
