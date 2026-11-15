"""The float32 baseline in exact_embed.py against onnxruntime on the model's own onnx/model.onnx.

On the first 100 sentences (one at a time, no padding), the cosine between the two vectors of each sentence must be
above 0.99999.

usage: python validate_float.py        (needs: pip install onnxruntime)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_embed as X  # noqa: E402

sentences, _ = X.sentences_and_scores()
sentences = sentences[:100]
tok = X.tokenizer()
f = X.embed(X.Float32(X.load_params()), tok, sentences, 1).astype(np.float64)
o = X.embed(X.Onnx(), tok, sentences, 1).astype(np.float64)
c = (f * o).sum(1) / np.linalg.norm(f, axis=1) / np.linalg.norm(o, axis=1)
print("float32 baseline against onnxruntime, %d sentences: cosine min %.8f, mean %.8f, max |difference| %.2e"
      % (len(sentences), c.min(), c.mean(), np.abs(f - o).max()))
sys.exit(0 if c.min() > 0.99999 else 1)
