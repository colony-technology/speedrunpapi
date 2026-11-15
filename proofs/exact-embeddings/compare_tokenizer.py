"""The plain-Python tokenizer in exact_embed.py against the `tokenizers` library, on every one of the 2,758 sentences.

The library reads the model's own tokenizer.json at the pinned revision. Both must give the same token ids,
including [CLS] and [SEP] and the truncation at 256.

usage: python compare_tokenizer.py        (needs: pip install tokenizers)
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_embed as X  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402

TOKENIZER_JSON = "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"

m = X.PINS["model"]
path = X.fetch("https://huggingface.co/%s/resolve/%s/tokenizer.json" % (m["repo"], m["revision"]),
               os.path.join(X.CACHE, "model", "tokenizer.json"), TOKENIZER_JSON)
lib = Tokenizer.from_file(path)
lib.enable_truncation(256)
lib.no_padding()                                   # tokenizer.json pads to 128; the model sees no padding
mine = X.tokenizer()
sentences, _ = X.sentences_and_scores()
diff, longest = 0, 0
for s in sentences:
    a = mine.encode(s)
    b = lib.encode(s).ids
    longest = max(longest, len(a))
    if a != b:
        diff += 1
        if diff <= 5:
            print("differs:", repr(s), a, b)
print("tokenizer: %d sentences, %d differences from tokenizers %s; longest %d tokens"
      % (len(sentences), diff, __import__("tokenizers").__version__, longest))
sys.exit(1 if diff else 0)
