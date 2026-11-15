"""The plain-Python tokenizer in exact_llm.py against the `tokenizers` library, both reading the pinned tokenizer.json.

Compared: the 64 prompts; each of the first 2,000 lines of the pinned text, with its newline; and those 2,000 lines
as one string. Every comparison must give the same token ids.

usage: python compare_tokenizer.py        (needs: pip install tokenizers)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402
import tokenizers  # noqa: E402

lib = tokenizers.Tokenizer.from_file(X.model_file("tokenizer.json"))
lib.no_padding()
lib.no_truncation()
mine = X.tokenizer()
lines = X.text().splitlines(keepends=True)[:2000]
cases = [("prompt", p) for p in X.prompts()] + [("line", l) for l in lines] + [("block", "".join(lines))]
diff, tokens = 0, 0
for kind, s in cases:
    a = mine.encode(s)
    b = lib.encode(s, add_special_tokens=True).ids
    tokens += len(a)
    if a != b:
        diff += 1
        if diff <= 5:
            print("differs (%s): %r\n  mine %s\n  lib  %s" % (kind, s[:80], a[:40], b[:40]))
print("tokenizer: %d strings (64 prompts, 2,000 lines, the 2,000 lines as one string), %d tokens, %d differences "
      "from tokenizers %s" % (len(cases), tokens, diff, tokenizers.__version__))
sys.exit(1 if diff else 0)
