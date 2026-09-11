from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from graph import investigate
from osiris_client import OsirisClient, READ_ONLY_TOOLS


app = FastAPI(title="OSIRIS AI Fusion", version="0.1.0")


class InvestigationRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


@app.get("/health")
async def health():
    client = OsirisClient()
    osiris = None
    try:
        osiris = await client.health()
    except Exception as exc:
        osiris = {"status": "unreachable", "error": str(exc)}
    return {
        "status": "operational",
        "service": "osiris-ai-fusion",
        "osiris": osiris,
        "read_only_tools": sorted(READ_ONLY_TOOLS),
    }


@app.post("/investigate")
async def investigate_route(body: InvestigationRequest):
    try:
        return await investigate(body.query)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
