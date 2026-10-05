from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class NLIVerdict(BaseModel):
    label: Literal["ENTAILMENT","CONTRADICTION","NEUTRAL"]
    entailment: float=Field(ge=0,le=1);contradiction: float=Field(ge=0,le=1);neutral: float=Field(ge=0,le=1)
    verifier: str

class NLIVerifier:
    """Deterministic verifier interface. Provider adapters can replace score()."""
    name="orbythra-nli-baseline-v1"
    def score(self, claim:str, evidence_text:str)->NLIVerdict:
        # Conservative lexical baseline: never invents entailment from a source id/URL.
        # Real NLI/LLM adapters must provide evidence text and calibrated probabilities.
        c={x.lower().strip(".,:;!?()[]") for x in claim.split() if x.strip(".,:;!?()[]") and x.lower().strip(".,:;!?()[]") not in {"not","no","never"}}
        e={x.lower().strip(".,:;!?()[]") for x in evidence_text.split() if x.strip(".,:;!?()[]") and x.lower().strip(".,:;!?()[]") not in {"not","no","never"}}
        overlap=len(c&e)/max(1,len(c))
        neg_claim=any(x in claim.lower().split() for x in ("not","no","never"))
        neg_ev=any(x in evidence_text.lower().split() for x in ("not","no","never"))
        contradiction=.98 if overlap>=.6 and neg_claim!=neg_ev else max(0.0,.15*(1-overlap))
        entailment=min(.95,overlap) if neg_claim==neg_ev else min(.25,overlap*.25)
        neutral=max(0.0,1-max(entailment,contradiction))
        total=entailment+contradiction+neutral
        entailment/=total;contradiction/=total;neutral/=total
        label="ENTAILMENT" if entailment>=.75 else ("CONTRADICTION" if contradiction>=.75 else "NEUTRAL")
        return NLIVerdict(label=label,entailment=round(entailment,6),contradiction=round(contradiction,6),neutral=round(neutral,6),verifier=self.name)

NLI=NLIVerifier()
