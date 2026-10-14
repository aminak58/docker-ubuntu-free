#!/usr/bin/env python3
"""Predeclared feed quality gate; remove likely synthetic flat padding, not real events."""
import csv, hashlib, json, pathlib
ROOT=pathlib.Path("runner-output")
SRC=ROOT/"xauusd_m1_bid.csv"
DST=ROOT/"xauusd_m1_bid_quality_checked.csv"
MIN_SYNTHETIC_RUN=5  # consecutive 1-minute bars with O==H==L==C

def main():
    with SRC.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    is_flat=[r["open"]==r["high"]==r["low"]==r["close"] for r in rows]
    rejected=[False]*len(rows)
    st=None;runs=[]
    for i,isflat in enumerate(is_flat+[False]):
        if isflat and st is None:
            st=i
        elif not isflat and st is not None:
            count=i-st
            if count>=MIN_SYNTHETIC_RUN:
                rejected[st:i]=[True]*count
                runs.append({"start_utc":rows[st]["time_utc"],
                             "end_utc":rows[i-1]["time_utc"],"count":count})
            st=None
    filtered=[row for row,drop in zip(rows,rejected) if not drop]
    if len(filtered)<50000:raise RuntimeError("too few quality-controlled bars")
    with DST.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader();w.writerows(filtered)
    audit={
       "quality_rule":"Exclude complete consecutive runs of 5+ zero-range (O=H=L=C) minute candles, treat removed minutes as missing gaps; never synthesize/reindex/forward-fill",
       "cutoff":MIN_SYNTHETIC_RUN,
       "raw_rows":len(rows),"raw_flat_rows":sum(is_flat),
       "rejected_rows":sum(rejected),"retained_rows":len(filtered),
       "rejected_runs":len(runs),"largest_rejected_run":max((r["count"] for r in runs),default=0),
       "first_rejected_runs":runs[:8],
       "cleaned_csv_sha256":hashlib.sha256(DST.read_bytes()).hexdigest(),
       "flags":["Third-party archived source contains synthetic extended flat intervals",
                "Cleaned sample uses only contiguous observed non-padded minute sequences",
                "Official provider provenance is declared by third-party mirror, not independently verified"]
    }
    (ROOT/"quality_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    print("QUALITY_RESULT="+json.dumps({k:v for k,v in audit.items() if k not in ("first_rejected_runs","flags")}),flush=True)
if __name__=="__main__":main()
