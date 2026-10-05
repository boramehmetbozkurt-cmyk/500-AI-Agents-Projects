from app.governed_agents_v7 import SimulationRequest,simulate
cases=[
({"action_id":"1","operation":"read","intended_effect":{"x":1},"predicted_effect":{"x":1},"reversible":False,"blast_radius":1},"ALLOW"),
({"action_id":"2","operation":"write","intended_effect":{"x":1},"predicted_effect":{"x":2},"reversible":True,"rollback_plan":{"x":0},"blast_radius":1},"BLOCK"),
({"action_id":"3","operation":"write","intended_effect":{"x":1},"predicted_effect":{"x":1},"reversible":True,"rollback_plan":None,"blast_radius":1},"REVIEW"),
({"action_id":"4","operation":"write","intended_effect":{"x":1},"predicted_effect":{"x":1},"reversible":True,"rollback_plan":{"x":0},"blast_radius":2000},"REVIEW")]
def main():
 passed=sum(simulate(SimulationRequest(**b)).decision==want for b,want in cases)
 if passed!=len(cases):raise SystemExit(f"v7 gate failed {passed}/{len(cases)}")
 print('{"schema":"orbythra.v7-governed-agents","passed":4,"total":4}')
if __name__=="__main__":main()
