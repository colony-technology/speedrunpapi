"""Prints the versions of Python, NumPy and SciPy that the replay runs on; exits 1 if NumPy or SciPy is missing."""
import sys

try:
    import numpy
    import scipy
except ImportError as e:
    print("missing: %s" % e.name)
    sys.exit(1)
print("Python", sys.version.split()[0], "NumPy", numpy.__version__, "SciPy", scipy.__version__)
