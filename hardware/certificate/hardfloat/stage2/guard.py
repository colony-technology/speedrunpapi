"""Memory and size guard for bvfsm searches.

A search calls Guard.tick(expanded, stored) as it goes. It stops with Stop when the number of stored
states passes BVFSM_MAX_STATES (default 3,000,000) or the process's peak resident memory passes
BVFSM_MAX_MB (default 2000 MB; the Mac's own guard stops any job over 2.8 GB). A stop means the result
is undecided: the search did not finish. Progress lines go to stderr.
"""
import os
import resource
import sys

MAX_STATES = int(os.environ.get("BVFSM_MAX_STATES", "3000000"))
MAX_MB = int(os.environ.get("BVFSM_MAX_MB", "2000"))


class Stop(Exception):
    pass


def rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1 << 20) if sys.platform == "darwin" else r / 1024.0     # bytes on macOS, kB on Linux


class Guard:
    def __init__(self, what):
        self.what = what

    def tick(self, expanded, stored):
        if stored > MAX_STATES:
            raise Stop("STOPPED %s: state cap %d reached (%d stored, %d expanded, peak %.0f MB); result undecided"
                       % (self.what, MAX_STATES, stored, expanded, rss_mb()))
        if expanded % 20000 == 0:
            mb = rss_mb()
            sys.stderr.write("  %s: %d stored, %d expanded, peak %.0f MB\n" % (self.what, stored, expanded, mb))
            sys.stderr.flush()
            if mb > MAX_MB:
                raise Stop("STOPPED %s: memory limit %d MB reached (peak %.0f MB, %d stored, %d expanded); "
                           "result undecided" % (self.what, MAX_MB, mb, stored, expanded))
