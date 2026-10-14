#!/usr/bin/env python3
"""Import pinned third-party archive of purported Dukascopy XAUUSD M1 BID (not direct source)."""
from __future__ import annotations
import csv, datetime as dt, hashlib, io, json, pathlib, urllib.request

OWNER_REPO="kevingtlin/Market-Data-Lab"
REV="922f83a60cc574e7395fb27397077288055a1ef6"
MONTHS=["2026_03","2026_04","2026_05","2026_06","2026_07","2026_08"]

def main():
    root=pathlib.Path("runner-output");root.mkdir(exist_ok=True)
    csv_path=root/"xauusd_m1_bid.csv"
    files=[]; n=0; last_ms=-1; first_time=None; last_time=None
    with csv_path.open("w",newline="",encoding="utf-8") as dst:
        writer=csv.writer(dst);writer.writerow(["time_utc","open","high","low","close","volume"])
        for month in MONTHS:
            url=f"https://raw.githubusercontent.com/{OWNER_REPO}/{REV}/xauusd/bid/m1/xauusd_bid_m1_{month}.csv"
            req=urllib.request.Request(url,headers={"User-Agent":"ResearchReproducibility/1.0"})
            with urllib.request.urlopen(req,timeout=50) as response:
                raw=response.read()
            audit={"month":month,"raw_url":url,"raw_sha256":hashlib.sha256(raw).hexdigest(),"rows":0}
            reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            if not {"timestamp","open","high","low","close"}.issubset(reader.fieldnames or []):
                raise ValueError(f"wrong CSV schema {month}: {reader.fieldnames}")
            for row in reader:
                stamp=int(row["timestamp"])
                if stamp <= last_ms:raise ValueError(f"timestamp out of order in {month}")
                if stamp % 60000:raise ValueError(f"not aligned to UTC minute {stamp}")
                t=dt.datetime.fromtimestamp(stamp/1000,tz=dt.timezone.utc)
                if t.strftime("%Y_%m") != month: raise ValueError(f"month mismatch {t} vs {month}")
                op,hi,lo,cl=(float(row[k]) for k in ("open","high","low","close"))
                if not (0<lo<=min(op,cl)<=max(op,cl)<=hi<100000):
                    raise ValueError(f"invalid OHLC {t}: {op,hi,lo,cl}")
                time_iso=t.strftime("%Y-%m-%dT%H:%M:%SZ")
                writer.writerow([time_iso,op,hi,lo,cl,0])
                first_time=first_time or time_iso;last_time=time_iso
                last_ms=stamp; n+=1; audit["rows"]+=1
            if audit["rows"]<1000:raise ValueError(f"month {month} too short: {audit['rows']}")
            print("MIRROR_MONTH="+json.dumps(audit),flush=True)
            files.append(audit)
    if n<75000:raise RuntimeError(f"insufficient archived bars {n}")
    summary={"variant":"EXP-ML-SWING-CONTINUATION-DUKASCOPY-M1",
        "declared_origin":"Dukascopy BID according to third-party archivist",
        "actual_retrieval":"GitHub public mirror, NOT direct Dukascopy",
        "direct_datafeed_provenance_verified":False,
        "mirror_repository":OWNER_REPO,"mirror_revision":REV,
        "timeframe":"M1","instrument":"XAUUSD","quote_side":"BID","timezone":"UTC",
        "volume_not_used":True,"rows":n,"first_utc":first_time,"last_utc":last_time,
        "csv_sha256":hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "files":files}
    (root/"daily_manifest.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print("MIRROR_DATA_RESULT="+json.dumps({k:summary[k] for k in ("rows","first_utc","last_utc","csv_sha256")}),flush=True)
if __name__=="__main__":main()
