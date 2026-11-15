"""usage: python3 -I zipget.py URL list
       python3 -I zipget.py URL get SUFFIX DEST_DIR [MAX_BYTES]
Members of a zip archive that sits on a web server, without downloading the archive: the central directory is
read by HTTP range requests, then each wanted member by its own range. `list` prints name and size of every
member. `get` saves every member whose name ends with SUFFIX and whose packed size is under MAX_BYTES (default
5,000,000) into DEST_DIR, the slashes of its name turned into double underscores. Nothing fetched is run."""
import os
import struct
import sys
import urllib.request
import zlib


def rng(url, a, b):
    req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (a, b), "User-Agent": "research-script/1.0"})
    return urllib.request.urlopen(req, timeout=60).read()


def directory(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "research-script/1.0"})
    size = int(urllib.request.urlopen(req, timeout=60).headers["Content-Length"])
    tail = rng(url, max(0, size - 131072), size - 1)
    i = tail.rfind(b"PK\x05\x06")
    cdsize, cdoff = struct.unpack("<II", tail[i + 12:i + 20])
    cd = rng(url, cdoff, cdoff + cdsize - 1)
    p, out = 0, []
    while cd[p:p + 4] == b"PK\x01\x02":
        meth = struct.unpack("<H", cd[p + 10:p + 12])[0]
        csz, usz = struct.unpack("<II", cd[p + 20:p + 28])
        fl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
        lo = struct.unpack("<I", cd[p + 42:p + 46])[0]
        name = cd[p + 46:p + 46 + fl].decode()
        p += 46 + fl + el + cl
        out.append((name, meth, csz, usz, lo))
    return out


def main(a):
    url, mode = a[1], a[2]
    members = directory(url)
    if mode == "list":
        for name, meth, csz, usz, lo in members:
            print("%12d  %s" % (usz, name))
        return
    suffix, dest = a[3], a[4]
    limit = int(a[5]) if len(a) > 5 else 5000000
    os.makedirs(dest, exist_ok=True)
    for name, meth, csz, usz, lo in members:
        if not name.endswith(suffix) or csz >= limit:
            continue
        target = os.path.join(dest, name.replace("/", "__"))
        if os.path.exists(target) and os.path.getsize(target) == usz:
            continue
        lh = rng(url, lo, lo + 29)
        n, e = struct.unpack("<HH", lh[26:30])
        raw = rng(url, lo + 30 + n + e, lo + 30 + n + e + csz - 1)
        data = raw if meth == 0 else zlib.decompress(raw, -15)
        open(target, "wb").write(data)
        print("%10d  %s" % (len(data), target))


if __name__ == "__main__":
    main(sys.argv)
