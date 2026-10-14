#!/usr/bin/env python3
"""XAUUSD M1 Dukascopy BID historical candle acquisition, UTC. No MT5 parity claims."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, lzma, pathlib, struct, time
import urllib.error, urllib.request

REC = struct.Struct(">IIIIIf")  # seconds, open, close, low, high, volume
SCALE = 1000.0
TZ = dt.timezone.utc

def day_url(day: dt.date) -> str:
    return (f"https://datafeed.dukascopy.com/datafeed/XAUUSD/{day.year}/"
            f"{day.month-1:02d}/{day.day:02d}/BID_candles_min_1.bi5")

def decode(blob: bytes, day: dt.date) -> list[tuple]:
    raw = lzma.decompress(blob, format=lzma.FORMAT_AUTO)
    if len(raw) % REC.size:
        raise ValueError(f"wrong record size on {day}: {len(raw)}")
    rows = []
    midnight = dt.datetime.combine(day, dt.time(), tzinfo=TZ)
    last = -60
    for sec, op, cl, lo, hi, vol in REC.iter_unpack(raw):
        if sec >= 86400 or sec % 60 or sec <= last:
            raise ValueError(f"invalid/inconsistent time {sec} on {day}")
        last = sec
        o,c,l,h = (x/SCALE for x in (op,cl,lo,hi))
        if not (l <= min(o,c) <= max(o,c) <= h and 0 < l <= h < 100000):
            raise ValueError(f"invalid OHLC: {day} {sec}: {o,c,l,h}")
        stamp = (midnight+dt.timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((stamp,o,h,l,c,vol))
    return rows

def get_day(day: dt.date) -> tuple[list[tuple],str,str]:
    url = day_url(day)
    for attempt in range(3):
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"ResearchReproducibility/1.0"})
            with urllib.request.urlopen(req, timeout=25) as f:
                blob=f.read()
            if not blob:
                return [],"EMPTY",""
            return decode(blob,day),"OK",hashlib.sha256(blob).hexdigest()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return [],"HTTP_404",""
            if attempt == 2: raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2: raise
        time.sleep(0.5 * (attempt+1))
    raise RuntimeError("unreachable")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--from-date", required=True)
    p.add_argument("--to-exclusive", required=True)
    p.add_argument("--outdir", required=True)
    args=p.parse_args()
    start=dt.date.fromisoformat(args.from_date); stop=dt.date.fromisoformat(args.to_exclusive)
    if not start < stop or (stop-start).days > 150:
        raise ValueError("date window must be 1..150 days")
    root=pathlib.Path(args.outdir); root.mkdir(parents=True,exist_ok=True)
    observations=[]; daily=[]
    day=start
    while day<stop:
        rows,status,digest=get_day(day)
        observations.extend(rows)
        daily.append(dict(date=str(day),status=status,rows=len(rows),url=day_url(day),raw_sha256=digest))
        print(f"{day}: {status} rows={len(rows)}",flush=True)
        day+=dt.timedelta(days=1)
    if len(observations) < 500:
        raise RuntimeError(f"insufficient market data: {len(observations)} bars")
    if any(x[0] >= y[0] for x,y in zip(observations,observations[1:])):
        raise AssertionError("non-increasing or duplicate UTC timestamps")
    with (root/"xauusd_m1_bid.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["time_utc","open","high","low","close","volume"])
        w.writerows(observations)
    with (root/"daily_manifest.json").open("w",encoding="utf-8") as f:
        json.dump({"instrument":"XAUUSD","provider":"Dukascopy","side":"BID","timeframe":"M1",
                   "utc":True,"data_is_not_mt5":True,"price_scale":SCALE,
                   "date_range":{"from":str(start),"to_exclusive":str(stop)},
                   "rows":len(observations),"daily":daily},f,indent=2)
    b=(root/"xauusd_m1_bid.csv").read_bytes()
    print("DATA_RESULT="+json.dumps({"rows":len(observations),"first":observations[0][0],
        "last":observations[-1][0],"csv_sha256":hashlib.sha256(b).hexdigest(),
        "nonempty_days":sum(bool(d["rows"]) for d in daily)},sort_keys=True))
if __name__=="__main__": main()
