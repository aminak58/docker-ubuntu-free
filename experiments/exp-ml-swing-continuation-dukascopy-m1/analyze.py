#!/usr/bin/env python3
"""Independent Dukascopy XAUUSD M1 swing/continuation experiment. Not an MT5 study."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, math, pathlib, random
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

H=12
BASE=["tk_gap_tr","body_dir_tr","momentum3_dir_tr"]
PLUS=BASE+["q25_price_dir_tr"]
LABELS=["y_tk","y_price","y_both"]

def mid(rows,i,n):
    r=rows[i-n+1:i+1]
    return (max(x["high"] for x in r)+min(x["low"] for x in r))/2

def tr(rows,i):
    x=rows[i]; prev=rows[i-1]["close"]
    return max(x["high"]-x["low"],abs(x["high"]-prev),abs(x["low"]-prev))

def read_rows(path):
    with open(path,newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        r["time"]=dt.datetime.fromisoformat(r["time_utc"].replace("Z","+00:00"))
        for k in ("open","high","low","close","volume"):
            r[k]=float(r[k])
    if any(b["time"] <= a["time"] for a,b in zip(rows,rows[1:])):
        raise AssertionError("unsorted time series")
    return rows

def iter_segments(rows):
    st=0
    for i in range(1,len(rows)):
        if (rows[i]["time"]-rows[i-1]["time"]).total_seconds()!=60:
            yield rows[st:i]
            st=i
    if st<len(rows): yield rows[st:]

def events_for(rows):
    events=[]
    counts={"continuous_segments":0,"segments_short":0,"crosses":0,"valid_swings":0,"right_censored":0}
    for s in iter_segments(rows):
        counts["continuous_segments"]+=1
        if len(s)<52:
            counts["segments_short"]+=1
            continue
        for i in range(51,len(s)):
            tn=mid(s,i,9);kn=mid(s,i,26)
            tp=mid(s,i-1,9);kp=mid(s,i-1,26)
            isbull=tp<=kp and tn>kn
            isbear=tp>=kp and tn<kn
            if not (isbull or isbear):continue
            counts["crosses"]+=1
            sign=1 if isbull else -1
            extreme_i=i
            extreme=s[i]["low"] if isbull else s[i]["high"]
            for age in range(1,20):
                j=i-age
                candidate=s[j]["low"] if isbull else s[j]["high"]
                if (isbull and candidate<extreme) or (isbear and candidate>extreme):
                    extreme=candidate;extreme_i=j
            age=i-extreme_i
            if age not in (9,10):continue
            tr14=sum(tr(s,j) for j in range(i-13,i+1))/14.0
            if tr14<=0:continue
            displacement=sign*(s[i]["close"]-extreme)
            strength=displacement/tr14/age
            if displacement<=0 or strength<0.30:continue
            counts["valid_swings"]+=1
            q25=mid(s,i-25,26)  # exact Kijun26[C-25], not displaced graphical plot
            first_gap=sign*(tn-kn)
            complete=(i+H<len(s))
            event={
                "event_id":hashlib.sha256(f"dukascopy|XAUUSD|BID|M1|{s[i]['time_utc']}|{sign}".encode()).hexdigest()[:20],
                "provider":"Dukascopy","instrument":"XAUUSD","quote_side":"BID","timeframe":"M1",
                "confirmation_time_utc":s[i]["time_utc"],"direction":"bull_floor" if isbull else "bear_ceiling",
                "level":extreme,"age_from_cross":age,"strength":strength,"mean_tr14":tr14,
                "confirmation_close":s[i]["close"],"q25_frozen":q25,
                "tk_gap_tr":first_gap/tr14,
                "body_dir_tr":sign*(s[i]["close"]-s[i]["open"])/tr14,
                "momentum3_dir_tr":sign*(s[i]["close"]-s[i-3]["close"])/tr14,
                "q25_price_dir_tr":sign*(s[i]["close"]-q25)/tr14,
                "label_status":"EXACT_CLOSE" if complete else "RIGHT_CENSORED",
                "outcome_end_utc":s[i+H]["time_utc"] if complete else "",
                "y_tk":"","y_price":"","y_both":""
            }
            if complete:
                spreads=[sign*(mid(s,k,9)-mid(s,k,26)) for k in range(i+1,i+H+1)]
                event["y_tk"]=int(all(v>0 for v in spreads) and spreads[-1]>first_gap)
                event["y_price"]=int(sign*(s[i+H]["close"]-s[i]["close"])>0)
                event["y_both"]=int(event["y_tk"] and event["y_price"])
            else:counts["right_censored"]+=1
            events.append(event)
    return events,counts

def pred_metrics(y,p):
    y=np.asarray(y,dtype=float);p=np.clip(np.asarray(p,dtype=float),1e-8,1-1e-8)
    brier=float(np.mean((y-p)**2))
    loss=float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p)))
    ece=0.0
    for a,b in zip(np.linspace(0,1,6)[:-1],np.linspace(0,1,6)[1:]):
        mask=(p>=a)&(p<b if b<1 else p<=b)
        if np.any(mask):ece+=float(np.mean(mask))*abs(float(np.mean(y[mask])-np.mean(p[mask])))
    return {"n":len(y),"positives":int(sum(y)),"prevalence":float(np.mean(y)),
            "brier":brier,"log_loss":loss,"ece5":ece}

def delta_ci_day(rows,a,b,seed=20261014):
    days=sorted({r["confirmation_time_utc"][:10] for r in rows})
    groups=[[i for i,r in enumerate(rows) if r["confirmation_time_utc"].startswith(day)] for day in days]
    if len(groups)<5:return None
    rg=random.Random(seed);out=[]
    aa=np.array(a);bb=np.array(b)
    for _ in range(400):
        ix=[i for _ in groups for i in groups[rg.randrange(len(groups))]]
        out.append(float(np.mean(aa[ix]-bb[ix])))
    return {"delta_mean":float(np.mean(aa-bb)),
            "ci95":list(np.quantile(out,[0.025,0.975]).astype(float)),
            "n_days":len(groups)}

def run_train(events):
    out={"scheme":{
       "train":["2026-06-01","2026-08-01"],
       "validation":["2026-08-03","2026-09-01"],
       "internal_test":["2026-09-03","2026-10-01"],
       "gap":"2 full days between partitions; >= 12-minute label horizon",
       "test_is_genuine_untouched_oos":False,
       "model":"LogisticRegression L2 C=1, StandardScaler trained only on train",
       "hyperparameter_search":False}}
    slices={}
    for name,(lo,hi) in (("train",("2026-06-01","2026-08-01")),
                         ("validation",("2026-08-03","2026-09-01")),
                         ("internal_test",("2026-09-03","2026-10-01"))):
        slices[name]=[r for r in events if r["label_status"]=="EXACT_CLOSE" and
                      lo<=r["confirmation_time_utc"][:10]<hi and
                      r["outcome_end_utc"][:10]<hi]
    out["counts"]={k:len(v) for k,v in slices.items()}
    if min(out["counts"].values())<35:
        out["status"]="INSUFFICIENT_PARTITION_SIZE"
        return out
    out["labels"]={}
    for label in LABELS:
        a={}
        ytrain=np.array([int(r[label]) for r in slices["train"]])
        if sum(ytrain)<15 or (len(ytrain)-sum(ytrain))<15:
            out["labels"][label]={"status":"INSUFFICIENT_CLASS_SUPPORT","positive_train":int(sum(ytrain))}
            continue
        fits={}
        for key,feats in (("M1",BASE),("M2",PLUS)):
            X=np.array([[r[f] for f in feats] for r in slices["train"]],dtype=float)
            model=make_pipeline(StandardScaler(),LogisticRegression(penalty="l2",C=1,max_iter=1000,random_state=20261014))
            model.fit(X,ytrain)
            fits[key]=model
        a["split"]={}
        for split,subset in slices.items():
            y=np.array([int(r[label]) for r in subset])
            probs={"M0":np.full(len(y),float(np.mean(ytrain)))}
            for key,feats in (("M1",BASE),("M2",PLUS)):
                X=np.array([[r[f] for f in feats] for r in subset],dtype=float)
                probs[key]=fits[key].predict_proba(X)[:,1]
            a["split"][split]={key:pred_metrics(y,p) for key,p in probs.items()}
            da=np.square(y-probs["M2"]); db=np.square(y-probs["M1"])
            a["split"][split]["M2_minus_M1_brier_day_bootstrap"]=delta_ci_day(subset,da,db)
        val=a["split"]["validation"];test=a["split"]["internal_test"]
        ci=test["M2_minus_M1_brier_day_bootstrap"]
        # Independent decision rule avoids any search/retuning on validation or test.
        if (val["M2"]["brier"]<val["M1"]["brier"] and
            test["M2"]["brier"]<test["M1"]["brier"] and
            test["M2"]["positives"]>=20 and ci and ci["ci95"][1]<0):
            a["incremental_q25_status"]="SUPPORTIVE_INTERNAL_ONLY"
        else:
            a["incremental_q25_status"]="NOT_DEMONSTRATED"
        out["labels"][label]=a
    out["status"]="INTERNAL_RESEARCH_COMPLETE"
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",required=True);p.add_argument("--outdir",required=True)
    p.add_argument("--mode",choices=["smoke","full"],required=True)
    args=p.parse_args();root=pathlib.Path(args.outdir);root.mkdir(parents=True,exist_ok=True)
    rows=read_rows(args.data)
    events,counters=events_for(rows)
    all_days=sorted({r["confirmation_time_utc"][:10] for r in events})
    adjacent=sum((dt.datetime.fromisoformat(b["confirmation_time_utc"].replace("Z","+00:00"))-
                  dt.datetime.fromisoformat(a["confirmation_time_utc"].replace("Z","+00:00"))).total_seconds()<=12*60
                  for a,b in zip(events,events[1:]))
    summary={"variant":"EXP-ML-SWING-CONTINUATION-DUKASCOPY-M1",
             "source":"Dukascopy XAUUSD M1 BID; not MT5", "label_horizon_bars":H,
             "labels":{
              "y_tk":"directed TK spread stays >0 on bars 1..12 and terminal spread > initial spread",
              "y_price":"directed close(C+12) > directed close(C)",
              "y_both":"y_tk and y_price"},
             "counts":counters, "event_days":len(all_days),
             "pairs_adjacent_within_12min":adjacent,"first_event":events[0]["confirmation_time_utc"] if events else None,
             "last_event":events[-1]["confirmation_time_utc"] if events else None}
    with (root/"events.csv").open("w",newline="",encoding="utf-8") as f:
        if events:
            w=csv.DictWriter(f,fieldnames=list(events[0]));w.writeheader();w.writerows(events)
    if args.mode=="full":summary["ml"]=run_train(events)
    with (root/"research_report.json").open("w",encoding="utf-8") as f:json.dump(summary,f,indent=2)
    print("RESEARCH_RESULT="+json.dumps(summary,sort_keys=True),flush=True)
    if args.mode=="smoke" and not events:raise RuntimeError("no structural event; check source/contract")
if __name__=="__main__":main()
