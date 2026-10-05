from app.nli_verifier_v51 import NLI
CASES=[
("Water freezes at zero degrees Celsius","Water freezes at zero degrees Celsius.","ENTAILMENT"),
("The server is online","The server is not online.","CONTRADICTION"),
("Paris is in France","The evidence discusses database backups.","NEUTRAL"),
("The valve is open","The valve is never open.","CONTRADICTION"),
("A causes B","A causes B under the stated conditions.","ENTAILMENT")]
def run():
 rows=[];correct=0;false_entail=0
 for c,e,want in CASES:
  v=NLI.score(c,e);ok=v.label==want;correct+=ok;false_entail+=v.label=="ENTAILMENT" and want!="ENTAILMENT";rows.append({"expected":want,"actual":v.label,"ok":ok})
 acc=correct/len(CASES);fer=false_entail/len(CASES)
 report={"suite":"frozen-nli-calibration-v1","cases":len(CASES),"accuracy":acc,"false_entailment_rate":fer,"rows":rows,"boundary":"Small deterministic regression/calibration gate; not an external semantic benchmark."}
 if acc<.8 or fer>.2:raise SystemExit(str(report))
 return report
if __name__=="__main__":
 import json;print(json.dumps(run(),indent=2))
