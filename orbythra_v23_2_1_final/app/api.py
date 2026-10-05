from __future__ import annotations

from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.adaptive import router as adaptive_router
from app.agent_execution import router as agent_execution_router
from app.agents import router as agents_router
from app.autonomy import router as autonomy_router
from app.enterprise import router as enterprise_router
from app.main import app


@app.exception_handler(OperationalError)
async def database_unavailable(request, exc):
    return JSONResponse(status_code=503, content={"detail": "database_unavailable"})
from app.generalist_api_v5 import router as generalist_v5_router
from app.release import router as release_router
from app.validation import router as validation_router
from app.validation_v45 import router as validation_v45_router
from app.validation_v5 import router as validation_v5_router
from app.hardening_api_v51 import router as hardening_v51_router
from app.model_output_assurance_v51 import router as model_output_assurance_v51_router
from app.web_evidence_v51 import router as web_evidence_v51_router
from app.verifiable_intelligence_api_v6 import router as verifiable_intelligence_v6_router
from app.governed_agents_api_v7 import router as governed_agents_v7_router
from app.temporal_reality_api_v8 import router as temporal_reality_v8_router
from app.distributed_verification_api_v9 import router as distributed_verification_v9_router
from app.ai_operating_layer_api_v10 import router as ai_operating_layer_v10_router
from app.model_adapters_api_v10 import router as model_adapters_v10_router
from app.causal_intelligence_api_v11 import router as causal_intelligence_v11_router
from app.observability_api import router as observability_router
from app.cognitive_hardening_api_v11h import router as cognitive_hardening_v11h_router
from app.attachments import router as attachments_router
from app.unified_answer_policy import router as unified_answer_router
from app.verification_firewall_v12 import router as verification_firewall_v12_router
from app.distributed_verification_v12 import router as distributed_verification_v12_router
from app.action_chain_v12 import router as action_chain_v12_router
from app.temporal_reality_v12 import router as temporal_reality_v12_router
from app.calibration_v15 import router as calibration_v15_router
from app.agent_control_plane_v15 import router as agent_control_v15_router
from app.effect_verification_v15 import router as effect_verification_v15_router
from app.multimodal_evidence_v15 import router as multimodal_evidence_v15_router
from app.visual_identity_assurance_v15 import router as visual_identity_v15_router
from app.action_chain_finalization_v15 import router as action_chain_finalization_v15_router
from app.failure_memory_v15 import router as failure_memory_v15_router
from app.long_generation_v15 import router as long_generation_v15_router
from app.continual_generalist_v16 import router as continual_generalist_v16_router
from app.hierarchical_generalist_v17 import router as hierarchical_generalist_v17_router
from app.governed_model_adaptation_v18 import router as governed_model_adaptation_v18_router
from app.planner_synthesis_v19 import router as planner_synthesis_v19_router
from app.planner_reflection_v19 import router as planner_reflection_v19_router
from app.learning_engine_v20 import router as learning_engine_v20_router
from app.skill_invention_v20 import router as skill_invention_v20_router
from app.multimodal_world_v20 import router as multimodal_world_v20_router
from app.assurance_lab_v21 import router as assurance_lab_v21_router
from app.verifiable_general_agent_v23 import router as verifiable_general_agent_v23_router
from app.verifiable_general_agent_v232 import router as verifiable_general_agent_v232_router

# Production composition root: stable controls through V12 plus the V15 final-hardening
# tranche. V15 adds calibration, execution-time agent control/kill switches,
# independently observed effect verification, multimodal provenance, visual identity
# assurance, signed action-chain finalization, persistent failure/regression memory,
# and resumable governed long-generation up to a 2,000,000-token aggregate budget.
app.include_router(enterprise_router)
app.include_router(release_router)
app.include_router(validation_router)
app.include_router(validation_v45_router)
app.include_router(validation_v5_router)
app.include_router(hardening_v51_router)
app.include_router(model_output_assurance_v51_router)
app.include_router(web_evidence_v51_router)
app.include_router(verifiable_intelligence_v6_router)
app.include_router(governed_agents_v7_router)
app.include_router(temporal_reality_v8_router)
app.include_router(distributed_verification_v9_router)
app.include_router(ai_operating_layer_v10_router)
app.include_router(model_adapters_v10_router)
app.include_router(causal_intelligence_v11_router)
app.include_router(observability_router)
app.include_router(cognitive_hardening_v11h_router)
app.include_router(unified_answer_router)
app.include_router(attachments_router)
app.include_router(verification_firewall_v12_router)
app.include_router(distributed_verification_v12_router)
app.include_router(action_chain_v12_router)
app.include_router(temporal_reality_v12_router)
app.include_router(calibration_v15_router)
app.include_router(agent_control_v15_router)
app.include_router(effect_verification_v15_router)
app.include_router(multimodal_evidence_v15_router)
app.include_router(visual_identity_v15_router)
app.include_router(action_chain_finalization_v15_router)
app.include_router(failure_memory_v15_router)
app.include_router(long_generation_v15_router)
app.include_router(continual_generalist_v16_router)
app.include_router(hierarchical_generalist_v17_router)
app.include_router(governed_model_adaptation_v18_router)
app.include_router(planner_synthesis_v19_router)
app.include_router(planner_reflection_v19_router)
app.include_router(learning_engine_v20_router)
app.include_router(skill_invention_v20_router)
app.include_router(multimodal_world_v20_router)
app.include_router(assurance_lab_v21_router)
app.include_router(verifiable_general_agent_v23_router)
app.include_router(verifiable_general_agent_v232_router)
app.include_router(agents_router)
app.include_router(agent_execution_router)
app.include_router(autonomy_router)
app.include_router(adaptive_router)
app.include_router(generalist_v5_router)
