"""One prompt of the check set for the rv32i run: writes RUN_DIR/tokens.bin (int64 count, then the token ids) and
the link RUN_DIR/t3k.blob, then prints the host kernel's (t3-token, 8 lanes, arm64) lines in the guest's format:
    pos P sha256 <SHA-256 of the 49,152 logits, int32 little-endian> next <greedy token>
usage: python prompt_host.py RUN_DIR [PROMPT]        (PROMPT: index in the 64 prompts, default 12, 5 tokens)
"""
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import exact_llm as X  # noqa: E402


def main(argv):
    run = argv[1]
    k = int(argv[2]) if len(argv) > 2 else 12
    ids = X.tokenizer().encode(X.prompts()[k])
    os.makedirs(run, exist_ok=True)
    np.array([len(ids)] + ids, dtype="<i8").tofile(os.path.join(run, "tokens.bin"))
    m = X.T3Token(lanes=1)
    link = os.path.join(run, "t3k.blob")
    if not os.path.lexists(link):
        os.symlink(m.blob, link)
    m.open(1, 64)
    print("prompt %d: %d tokens %s" % (k, len(ids), ids))
    for t, tok in enumerate(ids):
        lg, nxt = m.step([0], [tok], [t])
        print("pos %02x sha256 %s next %08x" % (t, hashlib.sha256(lg[0].astype("<i4").tobytes()).hexdigest(),
                                                 int(nxt[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
