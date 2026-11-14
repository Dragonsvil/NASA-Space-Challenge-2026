"""
Fill lst_min_night, lst_max_day, lst_range in targets_moon_south_pole.csv
from LRO Diviner Polar Cumulative Products (PCP, bolometric temperature, 240 m bins).

FILE FORMAT (official label pcp_avg_tbol_pols_sum_ltim01_240.lbl):
  fixed-length records of 59 bytes; record 1 is a header, then ~3.6 million rows:
  x, y (distance from pole / 1737.4 km), longitude, latitude, temperature (K).
  Rows are sorted by x, then y. Period: 5 July 2009 - 17 Feb 2019.
  96 local-time bins x 2 seasons (SUM, WIN) = 192 files of ~200 MB.

WHY THIS VERSION IS FASTER AND SAFER
  * Because the rows are sorted by x and every record has the same length, we find the byte range
    that holds the 28 x 28 km box with a binary search (tiny requests) and download ONLY that
    slice (~20 MB per file instead of ~200 MB). If the server does not allow partial downloads,
    the script falls back to streaming the whole file.
  * No silent data loss: a short or truncated download, an odd record length or an unreadable
    number stops the script with an error instead of being skipped.

Usage (from the folder that contains this script):
    python diviner_temps.py inspect     # one file: shows format, download size, sanity checks
    python diviner_temps.py run         # all selected files, computes, updates the CSV
    python diviner_temps.py run --yes   # same, without the confirmation question
"""
import sys, os, json, ssl, time, http.client, urllib.parse
import numpy as np
import pandas as pd

# --- settings ---------------------------------------------------------------
ROOT = ("https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/"
        "data_derived_pcp/diurnal/ltim/pols/")
SEASONS = ["SUM", "WIN"]          # summer + winter products, pooled together
BIN_STEP = 8                      # use every 4th local-time bin (1 = all 96 bins, slowest)
WORKERS = 4                       # files downloaded at the same time (set 1 if the server complains)
LOCAL_DIR = ""                    # optional: folder with .tab files you already downloaded by hand
CACHE = "diviner_cache"           # small per-file results (box rows only) are kept here
CSV_IN = "targets_moon_south_pole.csv"       # change the path if the CSV is elsewhere
CSV_OUT = "targets_moon_south_pole.csv"      # overwritten in place

HALF = 14000.0                    # half width of the box in metres: 28 x 28 km, pole at the centre
MARGIN_M = 600.0                  # extra margin (m) when choosing the byte range
MOON_R = 1737400.0                # mean lunar radius (m); x, y in the files are divided by this
REC = 59                          # record length in bytes (from the label)
TIMEOUT = 60                      # seconds without data before a request is abandoned
NODATA_BELOW = 1.0                # temperatures (K) below this are treated as missing

# local-time bins: NUM 1 = 00:00-00:15 h ... NUM 96 = 23:45-24:00 h (LTIM = (NUM-1)*0.25)
DAY_ALL = range(25, 73)           # 06-18 h
NIGHT_ALL = list(range(73, 97)) + list(range(1, 25))   # 18-06 h
# -----------------------------------------------------------------------------

CTX = ssl._create_unverified_context()   # PDS certificate is not trusted by Python on some Windows installs.
                                         # Acceptable here: public, read-only NASA data. Do not reuse for logins.
LAST_MODE = {"mode": None}

def pick(bins):
    return [n for n in bins if (n - 1) % BIN_STEP == 0]

def file_url(season, n):
    return f"{ROOT}pcp_avg_tbol_pols_{season.lower()}_ltim{n:02d}_240.tab"


class Unsorted(Exception):
    pass


class LocalFile:
    """Same interface as Remote, for a .tab file that is already on your disk."""
    def __init__(self, path):
        self.path, self.total, self.f = path, os.path.getsize(path), open(path, "rb")

    def close(self):
        self.f.close()

    def get_range(self, start, length, progress=False):
        self.f.seek(start)
        b = self.f.read(length)
        if len(b) != length:
            raise IOError(f"{self.path}: file is shorter than expected (incomplete download?)")
        return b

    def stream(self, chunk_bytes):
        if self.total % REC:
            raise IOError(f"{self.path}: size {self.total} is not a multiple of {REC} (incomplete download?)")
        self.f.seek(0)
        while True:
            b = self.f.read(chunk_bytes)
            if not b:
                break
            yield b


class Remote:
    """One HTTP connection that can fetch byte ranges or stream a whole file."""
    def __init__(self, url, tag=""):
        self.url, self.conn, self.total, self.tag = url, None, None, tag

    def _connect(self):
        u = urllib.parse.urlsplit(self.url)
        self.path = u.path + ("?" + u.query if u.query else "")
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        kw = {"context": CTX} if u.scheme == "https" else {}
        self.conn = cls(u.netloc, timeout=TIMEOUT, **kw)

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def _get(self, headers):
        for _ in range(5):
            if self.conn is None:
                self._connect()
            try:
                self.conn.request("GET", self.path, headers=headers)
                resp = self.conn.getresponse()
            except (OSError, http.client.HTTPException):
                self.close()
                raise
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.getheader("Location")
                resp.read()
                self.url = urllib.parse.urljoin(self.url, loc)
                self.close()
                continue
            return resp
        raise RuntimeError("too many redirects")

    def get_range(self, start, length, progress=False):
        """Return exactly `length` bytes starting at `start`, or None if the server ignores Range."""
        resp = self._get({"Range": f"bytes={start}-{start + length - 1}"})
        if resp.status != 206:
            self.close()                       # do not download a full body we did not ask for
            if resp.status == 200:
                return None
            raise IOError(f"HTTP {resp.status} for {self.url}")
        cr = resp.getheader("Content-Range", "")
        if "/" in cr and cr.rsplit("/", 1)[1].strip().isdigit():
            self.total = int(cr.rsplit("/", 1)[1])
        buf, last = bytearray(), 0
        while len(buf) < length:
            part = resp.read(min(1 << 20, length - len(buf)))
            if not part:
                self.close()
                raise IOError(f"short read: got {len(buf)} of {length} bytes")
            buf += part
            if progress and len(buf) - last >= 5 << 20:
                print(f"    [{self.tag}] {len(buf) / 1e6:.0f} MB ...", flush=True)
                last = len(buf)
        return bytes(buf)

    def stream(self, chunk_bytes):
        """Yield the whole file in chunks and check that all of it arrived."""
        resp = self._get({})
        if resp.status != 200:
            self.close()
            raise IOError(f"HTTP {resp.status} for {self.url}")
        cl = resp.getheader("Content-Length")
        expected = int(cl) if cl else None
        got, last = 0, 0
        while True:
            buf = bytearray()
            while len(buf) < chunk_bytes:
                part = resp.read(chunk_bytes - len(buf))
                if not part:
                    break
                buf += part
            if not buf:
                break
            got += len(buf)
            if got - last >= 20 << 20:
                print(f"    [{self.tag}] {got / 1e6:.0f} MB ...", flush=True)
                last = got
            yield bytes(buf)
        self.close()
        if expected is not None and got != expected:
            raise IOError(f"truncated download: got {got} of {expected} bytes")
        if got % REC:
            raise IOError(f"file size {got} is not a multiple of {REC} bytes")


def parse(buf, box_only=True):
    """Parse whole 59-byte records. Returns (x_norm, y_norm, rows) where rows = [T_K, lat, x_m, y_m]
    for the records inside the box. Raises on anything unexpected (no silent skipping)."""
    if len(buf) == 0 or len(buf) % REC:
        raise ValueError(f"{len(buf)} bytes is not a whole number of {REC}-byte records")
    a = np.frombuffer(buf, dtype=np.uint8).reshape(-1, REC)
    commas = np.flatnonzero(a[0] == 44)
    if commas.size != 4 or not (a[:, commas] == 44).all():
        raise ValueError("records are not the fixed-width 5-column format described in the label")
    edges = [-1, *commas.tolist(), REC]

    def field(rows, i):
        sub = np.ascontiguousarray(rows[:, edges[i] + 1:edges[i + 1]])
        s = np.char.strip(sub.view(f"S{sub.shape[1]}").ravel())
        try:
            return s.astype(float)
        except ValueError:
            bad = [v for v in s if not v.replace(b".", b"", 1).replace(b"-", b"", 1).replace(b"+", b"", 1).isdigit()][:3]
            raise ValueError(f"unreadable number(s) in file, e.g. {bad}") from None

    x, y = field(a, 0), field(a, 1)
    m = (np.abs(x * MOON_R) <= HALF) & (np.abs(y * MOON_R) <= HALF)
    sub = a[m]
    if sub.shape[0] == 0:
        return x, y, np.empty((0, 4))
    lat, t = field(sub, 3), field(sub, 4)
    return x, y, np.column_stack([t, lat, x[m] * MOON_R, y[m] * MOON_R])


def box_by_range(rm):
    """Download only the byte range that contains the box. Returns (rows, bytes_downloaded) or None."""
    head = rm.get_range(0, REC)
    if head is None or rm.total is None:
        return None
    if rm.total % REC:
        raise IOError(f"file size {rm.total} is not a multiple of {REC}")
    n = rm.total // REC - 1                         # data records (record 0 is the header)
    lo_x, hi_x = -(HALF + MARGIN_M) / MOON_R, (HALF + MARGIN_M) / MOON_R

    def x_of(k):
        rec = rm.get_range(REC * (k + 1), REC)
        return float(rec[:rec.index(b",")])

    def bound(target, strict):                      # first k with x >= target (or x > target)
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            xm = x_of(mid)
            if (xm <= target) if strict else (xm < target):
                lo = mid + 1
            else:
                hi = mid
        return lo

    k0, k1 = bound(lo_x, False), bound(hi_x, True)
    if k1 <= k0:
        raise Unsorted("no records found in the expected byte range")
    buf = rm.get_range(REC * (k0 + 1), REC * (k1 - k0), progress=True)
    x, y, rows = parse(buf)
    if np.diff(x).min() < -1e-9 or x.min() < lo_x - 1e-7 or x.max() > hi_x + 1e-7:
        raise Unsorted("rows are not sorted by x as assumed")
    return rows, len(buf)


def stream_box(season, n):
    """Return an array [T_K, lat_deg, x_m, y_m] for the rows inside the box. Cached in CACHE/."""
    os.makedirs(CACHE, exist_ok=True)
    cpath = cache_path(season, n)
    if os.path.exists(cpath):
        return np.load(cpath)
    url, t0 = file_url(season, n), time.time()
    local = os.path.join(LOCAL_DIR, os.path.basename(url)) if LOCAL_DIR else None
    for attempt in range(1, 4):
        rm = LocalFile(local) if local and os.path.exists(local) else Remote(url, f"{season} {n:02d}")
        try:
            print(f"{season} bin {n:02d}: {url}  (attempt {attempt})", flush=True)
            res = None
            try:
                res = box_by_range(rm)
            except Unsorted as e:
                print("  partial download not possible:", e, "-> streaming the whole file")
            if res is not None:
                rows, nbytes = res
                LAST_MODE["mode"] = "local file" if isinstance(rm, LocalFile) else "partial"
            else:
                LAST_MODE["mode"] = "full"
                first = True
                kept, nbytes = [], 0
                pending = b""
                for chunk in rm.stream(REC * 100_000):
                    data = pending + chunk
                    if first:                      # drop the header record
                        data, first = data[REC:], False
                    whole = len(data) // REC * REC
                    pending = data[whole:]
                    nbytes += len(chunk)
                    if whole:
                        kept.append(parse(data[:whole])[2])
                if pending:
                    raise IOError("file ended in the middle of a record")
                rows = np.vstack(kept) if kept else np.empty((0, 4))
            rm.close()
            break
        except Exception as e:
            rm.close()
            print("  failed:", e, flush=True)
            if attempt == 3:
                raise
            time.sleep(10)
    np.save(cpath, rows)
    print(f"  done: {len(rows)} rows in box, {nbytes / 1e6:.1f} MB downloaded, "
          f"{time.time() - t0:.0f} s ({LAST_MODE['mode']})", flush=True)
    return rows


def cache_path(season, n):
    return os.path.join(CACHE, f"box_{season}_{n:02d}.npy")


def prefetch(files):
    """Fetch all missing files, WORKERS at a time. Finished files are cached on disk."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    todo = [(s, n) for s, n in files if not os.path.exists(cache_path(s, n))]
    print(f"{len(files) - len(todo)} files already cached, {len(todo)} to fetch "
          f"({WORKERS} at a time)", flush=True)
    if not todo:
        return
    done = 0
    ex = ThreadPoolExecutor(max_workers=WORKERS)
    futs = [ex.submit(stream_box, s, n) for s, n in todo]
    try:
        for f in as_completed(futs):
            f.result()                              # re-raises the error if a file failed for good
            done += 1
            print(f"=== {done}/{len(todo)} files finished ===", flush=True)
    except BaseException:
        for f in futs:
            f.cancel()
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    ex.shutdown()


def temps(season, n):
    arr = stream_box(season, n)
    t = arr[:, 0]
    return t[t >= NODATA_BELOW]


def stats_for(bins):
    """Per-file (min, max, mean) inside the box for the given LTIM bins and all seasons."""
    mins, maxs, means = [], [], []
    for s in SEASONS:
        for n in bins:
            v = temps(s, n)
            if v.size:
                mins.append(v.min()); maxs.append(v.max()); means.append(v.mean())
    return mins, maxs, means


def inspect():
    url = file_url(SEASONS[0], 1)
    rm = Remote(url)
    head = rm.get_range(0, 5 * REC)
    print("first 4 records of", url)
    if head is None:
        print("  (server does not allow partial downloads: whole files will be streamed, ~200 MB each)")
        head = b""
    for i in range(0, 4 if head else 0):
        print("  ", head[i * REC:(i + 1) * REC].decode("ascii", "replace").rstrip())
    if rm.total:
        print(f"file size: {rm.total / 1e6:.0f} MB, {rm.total // REC - 1} data records")
    rm.close()
    print("\nfetching the box from this file ...")
    arr = stream_box(SEASONS[0], 1)
    t = arr[:, 0]
    print(f"\nrows inside the 28 x 28 km box : {len(arr)}   (expect roughly 10,000-13,600)")
    if len(arr):
        print(f"latitude of those rows         : {arr[:,1].min():.3f} to {arr[:,1].max():.3f} deg "
              "(expect about -90 to -89.35)")
        print(f"max |x|, |y| of those rows (m) : {abs(arr[:,2]).max():.0f}, {abs(arr[:,3]).max():.0f} "
              "(expect about 14000)")
        print(f"temperature in box, bin 1      : {t.min():.1f} to {t.max():.1f} K")
    print("\nIf the numbers look right, run:  python diviner_temps.py run")


def run(assume_yes=False):
    if not os.path.exists(CSV_IN):
        sys.exit(f"Cannot find {CSV_IN} in this folder. Put the CSV here or change CSV_IN/CSV_OUT at the top.")
    day, night = pick(DAY_ALL), pick(NIGHT_ALL)
    n_files = (len(day) + len(night)) * len(SEASONS)
    print(f"{n_files} files will be processed (BIN_STEP = {BIN_STEP}): about {n_files * 0.02:.1f} GB "
          f"of download with partial downloads, or {n_files * 0.2:.0f} GB if the server only allows "
          "whole files. Finished files are cached, so you can stop (Ctrl+C) and resume.")
    if not assume_yes and input("Continue? (y/n) ").strip().lower() != "y":
        return
    prefetch([(s, n) for s in SEASONS for n in day + night])
    n_mins, _, n_means = stats_for(night)
    _, d_maxs, d_means = stats_for(day)
    if not n_mins or not d_maxs:
        sys.exit("No data inside the box: run `inspect` and check the output.")

    K = 273.15
    res = {
        "lst_min_night_C": round(min(n_mins) - K, 1),
        "lst_max_day_C": round(max(d_maxs) - K, 1),
        "lst_range_C": round(float(np.mean(d_means) - np.mean(n_means)), 1),  # difference of means
        "mean_night_C": round(float(np.mean(n_means)) - K, 1),
        "mean_day_C": round(float(np.mean(d_means)) - K, 1),
        "files_used_night": len(n_mins), "files_used_day": len(d_maxs),
        "bin_step": BIN_STEP,
        "note": "min/max are over individual 240 m bins; ask C whether Jezero used tile extremes or tile means",
    }
    print(json.dumps(res, indent=2))
    json.dump(res, open("diviner_result.json", "w"), indent=2)

    src = ("LRO Diviner Polar Cumulative Products (diurnal, south pole), bolometric temperature, 240 m bins, "
           "28x28 km box centred on pole, summer+winter pooled, nadir observations 5 Jul 2009 - 17 Feb 2019 "
           f"(per label), every {BIN_STEP}th 0.25 h local-time bin; computed with diviner_temps.py")
    df = pd.read_csv(CSV_IN, keep_default_na=False)      # keep the text "NA" as is
    df["value"] = df["value"].astype(object)
    for feat, val in [("lst_min_night", res["lst_min_night_C"]),
                      ("lst_max_day", res["lst_max_day_C"]),
                      ("lst_range", res["lst_range_C"])]:
        m = (df.target == "moon_south_pole") & (df.feature == feat)
        df.loc[m, "value"] = val
        df.loc[m, "source"] = src
    df.to_csv(CSV_OUT, index=False)
    print("updated", CSV_OUT)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "inspect":
        inspect()
    elif cmd == "run":
        run("--yes" in sys.argv)
    else:
        print(__doc__)