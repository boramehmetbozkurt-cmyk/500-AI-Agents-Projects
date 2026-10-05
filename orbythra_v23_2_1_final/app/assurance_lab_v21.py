from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections import defaultdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.telemetry import OTEL
from app.vault import VAULT

router = APIRouter(prefix="/v21/assurance", tags=["v21-assurance-lab"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_TRACE_ID_PATTERN = r"^[0-9a-f]{32}$"
_SPAN_ID_PATTERN = r"^[0-9a-f]{16}$"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False, default=str)


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class DatasetRecord(BaseModel):
    dataset_id: str
    name: str
    description: str
    created_at: int


class DatasetExample(BaseModel):
    input: Any
    expected_output: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetVersionCreate(BaseModel):
    examples: list[DatasetExample] = Field(min_length=1, max_length=10_000)
    label: str = Field(default="candidate", min_length=1, max_length=120)
    source_refs: list[str] = Field(default_factory=list, max_length=500)


class DatasetVersion(BaseModel):
    dataset_id: str
    version_id: str
    version_number: int
    label: str
    sha256: str
    example_count: int
    source_refs: list[str]
    created_at: int


class DatasetVersionContent(DatasetVersion):
    examples: list[DatasetExample]


class PromptVersionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    template: str = Field(min_length=1, max_length=200_000)
    model_id: str | None = Field(default=None, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=100)


class PromptVersion(BaseModel):
    prompt_id: str
    name: str
    version_id: str
    version_number: int
    sha256: str
    model_id: str | None
    tags: list[str]
    created_at: int


class PromptVersionContent(PromptVersion):
    template: str
    parameters: dict[str, Any]


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dataset_version_id: str = Field(min_length=1, max_length=120)
    prompt_version_id: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentRecord(BaseModel):
    experiment_id: str
    name: str
    dataset_version_id: str
    prompt_version_id: str
    model_id: str
    frozen_input_sha256: str
    status: Literal["OPEN", "SEALED"]
    created_at: int
    updated_at: int


class ExperimentResultItem(BaseModel):
    example_index: int = Field(ge=0, le=10_000_000)
    repetition: int = Field(default=0, ge=0, le=10_000)
    output: Any
    scores: dict[str, float] = Field(default_factory=dict)
    latency_ms: float = Field(default=0.0, ge=0.0, le=86_400_000.0)
    input_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    output_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    cost_usd: float = Field(default=0.0, ge=0.0, le=1_000_000_000.0)
    trace_id: str | None = Field(default=None, pattern=_TRACE_ID_PATTERN)

    @field_validator("scores")
    @classmethod
    def finite_scores(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 100:
            raise ValueError("too_many_scores")
        if any(not math.isfinite(float(score)) for score in value.values()):
            raise ValueError("non_finite_score")
        return value


class ExperimentResultsSubmit(BaseModel):
    items: list[ExperimentResultItem] = Field(min_length=1, max_length=20_000)
    seal_after_submit: bool = False


class ExperimentSummary(BaseModel):
    experiment_id: str
    result_count: int
    aggregate_scores: dict[str, float]
    average_latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: Literal["OPEN", "SEALED"]
    summary_sha256: str


class ExperimentComparisonRequest(BaseModel):
    baseline_experiment_id: str = Field(min_length=1, max_length=120)
    candidate_experiment_id: str = Field(min_length=1, max_length=120)
    primary_metric: str = Field(min_length=1, max_length=120)
    minimum_improvement: float = Field(default=0.0, ge=-1_000_000.0, le=1_000_000.0)


class ExperimentComparison(BaseModel):
    baseline_experiment_id: str
    candidate_experiment_id: str
    primary_metric: str
    baseline_score: float
    candidate_score: float
    delta: float
    minimum_improvement: float
    passed: bool
    comparison_sha256: str


class TraceSpanIngest(BaseModel):
    trace_id: str = Field(pattern=_TRACE_ID_PATTERN)
    span_id: str = Field(pattern=_SPAN_ID_PATTERN)
    parent_span_id: str | None = Field(default=None, pattern=_SPAN_ID_PATTERN)
    name: str = Field(min_length=1, max_length=300)
    kind: Literal["INTERNAL", "SERVER", "CLIENT", "PRODUCER", "CONSUMER"] = "INTERNAL"
    start_time_unix_nano: int = Field(ge=1)
    end_time_unix_nano: int = Field(ge=1)
    status: Literal["UNSET", "OK", "ERROR"] = "UNSET"
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_manifest_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    policy_decision_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    outcome_receipt_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @field_validator("attributes")
    @classmethod
    def bounded_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 200:
            raise ValueError("too_many_trace_attributes")
        if len(_json(value).encode("utf-8")) > 128_000:
            raise ValueError("trace_attributes_too_large")
        return value


class TraceSpanRecord(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    status: str
    duration_ms: float
    lineage_sha256: str
    evidence_manifest_sha256: str | None
    policy_decision_sha256: str | None
    outcome_receipt_sha256: str | None


class TraceLineage(BaseModel):
    trace_id: str
    span_count: int
    bound_span_count: int
    cryptographic_chain_complete: bool
    trace_sha256: str
    boundary: str = (
        "V21 binds trace spans to supplied evidence, policy and outcome-receipt hashes. "
        "A complete hash binding proves linkage/integrity of supplied references; it does not by itself prove external factual truth."
    )


class AssuranceLabV21:
    def __init__(self) -> None:
        self.engine = STORE.engine
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS datasets_v21(
                workspace_id TEXT NOT NULL,dataset_id TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,
                created_at BIGINT NOT NULL,PRIMARY KEY(workspace_id,dataset_id),UNIQUE(workspace_id,name))"""
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS dataset_versions_v21(
                workspace_id TEXT NOT NULL,dataset_id TEXT NOT NULL,version_id TEXT NOT NULL,version_number INTEGER NOT NULL,
                label TEXT NOT NULL,payload_json TEXT NOT NULL,source_refs_json TEXT NOT NULL,sha256 TEXT NOT NULL,
                example_count INTEGER NOT NULL,created_at BIGINT NOT NULL,PRIMARY KEY(workspace_id,version_id),
                UNIQUE(workspace_id,dataset_id,version_number))"""
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS prompts_v21(
                workspace_id TEXT NOT NULL,prompt_id TEXT NOT NULL,name TEXT NOT NULL,created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,prompt_id),UNIQUE(workspace_id,name))"""
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS prompt_versions_v21(
                workspace_id TEXT NOT NULL,prompt_id TEXT NOT NULL,version_id TEXT NOT NULL,version_number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,sha256 TEXT NOT NULL,model_id TEXT,tags_json TEXT NOT NULL,created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,version_id),UNIQUE(workspace_id,prompt_id,version_number))"""
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS experiments_v21(
                workspace_id TEXT NOT NULL,experiment_id TEXT NOT NULL,name TEXT NOT NULL,dataset_version_id TEXT NOT NULL,
                prompt_version_id TEXT NOT NULL,model_id TEXT NOT NULL,metadata_json TEXT NOT NULL,frozen_input_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,created_at BIGINT NOT NULL,updated_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,experiment_id))"""
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS experiment_results_v21(
                workspace_id TEXT NOT NULL,experiment_id TEXT NOT NULL,result_id TEXT NOT NULL,example_index INTEGER NOT NULL,
                repetition INTEGER NOT NULL,output_json TEXT NOT NULL,scores_json TEXT NOT NULL,latency_ms REAL NOT NULL,
                input_tokens BIGINT NOT NULL,output_tokens BIGINT NOT NULL,cost_usd REAL NOT NULL,trace_id TEXT,
                created_at BIGINT NOT NULL,PRIMARY KEY(workspace_id,result_id),
                UNIQUE(workspace_id,experiment_id,example_index,repetition))"""
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS trace_spans_v21(
                workspace_id TEXT NOT NULL,trace_id TEXT NOT NULL,span_id TEXT NOT NULL,parent_span_id TEXT,name TEXT NOT NULL,
                kind TEXT NOT NULL,start_ns BIGINT NOT NULL,end_ns BIGINT NOT NULL,status TEXT NOT NULL,attributes_json TEXT NOT NULL,
                evidence_manifest_sha256 TEXT,policy_decision_sha256 TEXT,outcome_receipt_sha256 TEXT,
                lineage_sha256 TEXT NOT NULL,created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,trace_id,span_id))"""
            ))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_dataset_versions_v21 ON dataset_versions_v21(workspace_id,dataset_id,version_number)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_experiment_results_v21 ON experiment_results_v21(workspace_id,experiment_id,example_index)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_trace_spans_v21 ON trace_spans_v21(workspace_id,trace_id,start_ns)"))

    def create_dataset(self, workspace_id: str, body: DatasetCreate) -> DatasetRecord:
        dataset_id = "ds21_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        try:
            with self.engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO datasets_v21(workspace_id,dataset_id,name,description,created_at) VALUES(:w,:id,:name,:description,:created)"
                ), {"w": workspace_id, "id": dataset_id, "name": body.name, "description": body.description, "created": now})
        except IntegrityError as exc:
            if "UNIQUE" in str(exc).upper() or "DUPLICATE" in str(exc).upper():
                raise ValueError("dataset_name_already_exists") from exc
            raise
        return DatasetRecord(dataset_id=dataset_id, name=body.name, description=body.description, created_at=now)

    def create_dataset_version(self, workspace_id: str, dataset_id: str, body: DatasetVersionCreate) -> DatasetVersion:
        with self.engine.connect() as connection:
            dataset = connection.execute(text(
                "SELECT dataset_id FROM datasets_v21 WHERE workspace_id=:w AND dataset_id=:id"
            ), {"w": workspace_id, "id": dataset_id}).first()
            if dataset is None:
                raise LookupError("dataset_not_found")
            current = connection.execute(text(
                "SELECT COALESCE(MAX(version_number),0) FROM dataset_versions_v21 WHERE workspace_id=:w AND dataset_id=:id"
            ), {"w": workspace_id, "id": dataset_id}).scalar_one()
        version_number = int(current) + 1
        version_id = "dsv21_" + uuid.uuid4().hex[:24]
        examples = [item.model_dump(mode="json") for item in body.examples]
        digest = _hash({
            "dataset_id": dataset_id,
            "version_number": version_number,
            "label": body.label,
            "examples": examples,
            "source_refs": body.source_refs,
        })
        now = int(time.time())
        encrypted = VAULT.encrypt_json(examples, workspace_id=workspace_id, purpose="dataset-v21")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO dataset_versions_v21(
                workspace_id,dataset_id,version_id,version_number,label,payload_json,source_refs_json,sha256,example_count,created_at
                ) VALUES(:w,:dataset,:version,:number,:label,:payload,:refs,:sha,:count,:created)"""
            ), {
                "w": workspace_id, "dataset": dataset_id, "version": version_id, "number": version_number,
                "label": body.label, "payload": encrypted, "refs": _json(body.source_refs),
                "sha": digest, "count": len(examples), "created": now,
            })
        return DatasetVersion(
            dataset_id=dataset_id, version_id=version_id, version_number=version_number, label=body.label,
            sha256=digest, example_count=len(examples), source_refs=body.source_refs, created_at=now,
        )

    def create_prompt_version(self, workspace_id: str, body: PromptVersionCreate) -> PromptVersion:
        now = int(time.time())
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT prompt_id FROM prompts_v21 WHERE workspace_id=:w AND name=:name"
            ), {"w": workspace_id, "name": body.name}).mappings().first()
        prompt_id = str(row["prompt_id"]) if row else "pr21_" + uuid.uuid4().hex[:24]
        if row is None:
            with self.engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO prompts_v21(workspace_id,prompt_id,name,created_at) VALUES(:w,:id,:name,:created)"
                ), {"w": workspace_id, "id": prompt_id, "name": body.name, "created": now})
        with self.engine.connect() as connection:
            current = connection.execute(text(
                "SELECT COALESCE(MAX(version_number),0) FROM prompt_versions_v21 WHERE workspace_id=:w AND prompt_id=:id"
            ), {"w": workspace_id, "id": prompt_id}).scalar_one()
        number = int(current) + 1
        version_id = "prv21_" + uuid.uuid4().hex[:24]
        payload = {
            "template": body.template,
            "model_id": body.model_id,
            "parameters": body.parameters,
            "tags": body.tags,
        }
        digest = _hash({"prompt_id": prompt_id, "version_number": number, **payload})
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO prompt_versions_v21(
                workspace_id,prompt_id,version_id,version_number,payload_json,sha256,model_id,tags_json,created_at
                ) VALUES(:w,:prompt,:version,:number,:payload,:sha,:model,:tags,:created)"""
            ), {
                "w": workspace_id, "prompt": prompt_id, "version": version_id, "number": number,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="prompt-v21"),
                "sha": digest, "model": body.model_id, "tags": _json(body.tags), "created": now,
            })
        return PromptVersion(
            prompt_id=prompt_id, name=body.name, version_id=version_id, version_number=number,
            sha256=digest, model_id=body.model_id, tags=body.tags, created_at=now,
        )

    def get_dataset_version(self, workspace_id: str, version_id: str) -> DatasetVersionContent | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                """SELECT dataset_id,version_id,version_number,label,payload_json,source_refs_json,sha256,example_count,created_at
                FROM dataset_versions_v21 WHERE workspace_id=:w AND version_id=:id"""
            ), {"w": workspace_id, "id": version_id}).mappings().first()
        if row is None:
            return None
        examples = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="dataset-v21")
        return DatasetVersionContent(
            dataset_id=row["dataset_id"],
            version_id=row["version_id"],
            version_number=int(row["version_number"]),
            label=row["label"],
            sha256=row["sha256"],
            example_count=int(row["example_count"]),
            source_refs=list(json.loads(row["source_refs_json"])),
            created_at=int(row["created_at"]),
            examples=[DatasetExample.model_validate(item) for item in examples],
        )

    def get_prompt_version(self, workspace_id: str, version_id: str) -> PromptVersionContent | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                """SELECT p.name,v.prompt_id,v.version_id,v.version_number,v.payload_json,v.sha256,v.model_id,v.tags_json,v.created_at
                FROM prompt_versions_v21 v
                JOIN prompts_v21 p ON p.workspace_id=v.workspace_id AND p.prompt_id=v.prompt_id
                WHERE v.workspace_id=:w AND v.version_id=:id"""
            ), {"w": workspace_id, "id": version_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="prompt-v21")
        return PromptVersionContent(
            prompt_id=row["prompt_id"],
            name=row["name"],
            version_id=row["version_id"],
            version_number=int(row["version_number"]),
            sha256=row["sha256"],
            model_id=row["model_id"],
            tags=list(json.loads(row["tags_json"])),
            created_at=int(row["created_at"]),
            template=str(payload["template"]),
            parameters=dict(payload.get("parameters") or {}),
        )

    def _version_hash(self, workspace_id: str, table: str, version_id: str) -> str | None:
        if table not in {"dataset_versions_v21", "prompt_versions_v21"}:
            raise ValueError("invalid_version_table")
        with self.engine.connect() as connection:
            row = connection.execute(text(
                f"SELECT sha256 FROM {table} WHERE workspace_id=:w AND version_id=:id"
            ), {"w": workspace_id, "id": version_id}).first()
        return None if row is None else str(row[0])

    def create_experiment(self, workspace_id: str, body: ExperimentCreate) -> ExperimentRecord:
        dataset_sha = self._version_hash(workspace_id, "dataset_versions_v21", body.dataset_version_id)
        prompt_sha = self._version_hash(workspace_id, "prompt_versions_v21", body.prompt_version_id)
        if dataset_sha is None:
            raise LookupError("dataset_version_not_found")
        if prompt_sha is None:
            raise LookupError("prompt_version_not_found")
        experiment_id = "exp21_" + uuid.uuid4().hex[:24]
        frozen = _hash({
            "dataset_sha256": dataset_sha,
            "prompt_sha256": prompt_sha,
            "model_id": body.model_id,
            "metadata": body.metadata,
        })
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO experiments_v21(
                workspace_id,experiment_id,name,dataset_version_id,prompt_version_id,model_id,metadata_json,
                frozen_input_sha256,status,created_at,updated_at
                ) VALUES(:w,:id,:name,:dataset,:prompt,:model,:metadata,:frozen,'OPEN',:created,:updated)"""
            ), {
                "w": workspace_id, "id": experiment_id, "name": body.name,
                "dataset": body.dataset_version_id, "prompt": body.prompt_version_id, "model": body.model_id,
                "metadata": VAULT.encrypt_json(body.metadata, workspace_id=workspace_id, purpose="experiment-v21"),
                "frozen": frozen, "created": now, "updated": now,
            })
        return ExperimentRecord(
            experiment_id=experiment_id, name=body.name, dataset_version_id=body.dataset_version_id,
            prompt_version_id=body.prompt_version_id, model_id=body.model_id, frozen_input_sha256=frozen,
            status="OPEN", created_at=now, updated_at=now,
        )

    def _experiment(self, workspace_id: str, experiment_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM experiments_v21 WHERE workspace_id=:w AND experiment_id=:id"
            ), {"w": workspace_id, "id": experiment_id}).mappings().first()
        return None if row is None else dict(row)

    def submit_results(self, workspace_id: str, experiment_id: str, body: ExperimentResultsSubmit) -> ExperimentSummary:
        experiment = self._experiment(workspace_id, experiment_id)
        if experiment is None:
            raise LookupError("experiment_not_found")
        if experiment["status"] != "OPEN":
            raise ValueError("experiment_is_sealed")
        with self.engine.connect() as connection:
            example_count = connection.execute(text(
                "SELECT example_count FROM dataset_versions_v21 WHERE workspace_id=:w AND version_id=:id"
            ), {"w": workspace_id, "id": experiment["dataset_version_id"]}).scalar_one_or_none()
        if example_count is None:
            raise RuntimeError("experiment_dataset_version_missing")
        if any(item.example_index >= int(example_count) for item in body.items):
            raise ValueError("experiment_example_index_out_of_range")
        now = int(time.time())
        with self.engine.begin() as connection:
            for item in body.items:
                result_id = "res21_" + uuid.uuid4().hex[:24]
                try:
                    connection.execute(text(
                        """INSERT INTO experiment_results_v21(
                        workspace_id,experiment_id,result_id,example_index,repetition,output_json,scores_json,latency_ms,
                        input_tokens,output_tokens,cost_usd,trace_id,created_at
                        ) VALUES(:w,:experiment,:id,:index,:repetition,:output,:scores,:latency,:input_tokens,:output_tokens,:cost,:trace,:created)"""
                    ), {
                        "w": workspace_id, "experiment": experiment_id, "id": result_id,
                        "index": item.example_index, "repetition": item.repetition,
                        "output": VAULT.encrypt_json(item.output, workspace_id=workspace_id, purpose="experiment-result-v21"),
                        "scores": _json(item.scores), "latency": item.latency_ms,
                        "input_tokens": item.input_tokens, "output_tokens": item.output_tokens,
                        "cost": item.cost_usd, "trace": item.trace_id, "created": now,
                    })
                except IntegrityError as exc:
                    if "UNIQUE" in str(exc).upper() or "DUPLICATE" in str(exc).upper():
                        raise ValueError("experiment_result_already_exists") from exc
                    raise
            if body.seal_after_submit:
                covered = connection.execute(text(
                    """SELECT COUNT(DISTINCT example_index) FROM experiment_results_v21
                    WHERE workspace_id=:w AND experiment_id=:id"""
                ), {"w": workspace_id, "id": experiment_id}).scalar_one()
                if int(covered) != int(example_count):
                    raise ValueError("experiment_cannot_seal_incomplete_dataset")
                connection.execute(text(
                    "UPDATE experiments_v21 SET status='SEALED',updated_at=:updated WHERE workspace_id=:w AND experiment_id=:id"
                ), {"updated": now, "w": workspace_id, "id": experiment_id})
            else:
                connection.execute(text(
                    "UPDATE experiments_v21 SET updated_at=:updated WHERE workspace_id=:w AND experiment_id=:id"
                ), {"updated": now, "w": workspace_id, "id": experiment_id})
        return self.summary(workspace_id, experiment_id)

    def summary(self, workspace_id: str, experiment_id: str) -> ExperimentSummary:
        experiment = self._experiment(workspace_id, experiment_id)
        if experiment is None:
            raise LookupError("experiment_not_found")
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """SELECT scores_json,latency_ms,input_tokens,output_tokens,cost_usd
                FROM experiment_results_v21 WHERE workspace_id=:w AND experiment_id=:id"""
            ), {"w": workspace_id, "id": experiment_id}).mappings().all()
        scores: dict[str, list[float]] = defaultdict(list)
        latency = 0.0
        input_tokens = 0
        output_tokens = 0
        cost = 0.0
        for row in rows:
            for key, value in json.loads(row["scores_json"]).items():
                scores[str(key)].append(float(value))
            latency += float(row["latency_ms"])
            input_tokens += int(row["input_tokens"])
            output_tokens += int(row["output_tokens"])
            cost += float(row["cost_usd"])
        aggregates = {key: round(sum(values) / len(values), 8) for key, values in sorted(scores.items()) if values}
        result_count = len(rows)
        summary_body = {
            "experiment_id": experiment_id,
            "result_count": result_count,
            "aggregate_scores": aggregates,
            "average_latency_ms": round(latency / result_count, 6) if result_count else 0.0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 8),
            "status": experiment["status"],
            "frozen_input_sha256": experiment["frozen_input_sha256"],
        }
        return ExperimentSummary(
            experiment_id=experiment_id,
            result_count=result_count,
            aggregate_scores=aggregates,
            average_latency_ms=summary_body["average_latency_ms"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=summary_body["cost_usd"],
            status=experiment["status"],
            summary_sha256=_hash(summary_body),
        )

    def compare(self, workspace_id: str, body: ExperimentComparisonRequest) -> ExperimentComparison:
        baseline_record = self._experiment(workspace_id, body.baseline_experiment_id)
        candidate_record = self._experiment(workspace_id, body.candidate_experiment_id)
        if baseline_record is None or candidate_record is None:
            raise LookupError("experiment_not_found")
        if baseline_record["status"] != "SEALED" or candidate_record["status"] != "SEALED":
            raise ValueError("experiment_comparison_requires_sealed")
        if baseline_record["dataset_version_id"] != candidate_record["dataset_version_id"]:
            raise ValueError("experiment_comparison_dataset_mismatch")
        if baseline_record["prompt_version_id"] != candidate_record["prompt_version_id"]:
            raise ValueError("experiment_comparison_prompt_mismatch")
        baseline = self.summary(workspace_id, body.baseline_experiment_id)
        candidate = self.summary(workspace_id, body.candidate_experiment_id)
        if body.primary_metric not in baseline.aggregate_scores:
            raise ValueError("baseline_metric_missing")
        if body.primary_metric not in candidate.aggregate_scores:
            raise ValueError("candidate_metric_missing")
        baseline_score = baseline.aggregate_scores[body.primary_metric]
        candidate_score = candidate.aggregate_scores[body.primary_metric]
        delta = round(candidate_score - baseline_score, 8)
        comparison = {
            "baseline_experiment_id": body.baseline_experiment_id,
            "candidate_experiment_id": body.candidate_experiment_id,
            "primary_metric": body.primary_metric,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "delta": delta,
            "minimum_improvement": body.minimum_improvement,
            "passed": delta >= body.minimum_improvement,
        }
        return ExperimentComparison(**comparison, comparison_sha256=_hash(comparison))

    def ingest_span(self, workspace_id: str, body: TraceSpanIngest) -> TraceSpanRecord:
        if body.end_time_unix_nano < body.start_time_unix_nano:
            raise ValueError("trace_end_before_start")
        lineage = {
            "trace_id": body.trace_id,
            "span_id": body.span_id,
            "parent_span_id": body.parent_span_id,
            "name": body.name,
            "kind": body.kind,
            "start_time_unix_nano": body.start_time_unix_nano,
            "end_time_unix_nano": body.end_time_unix_nano,
            "status": body.status,
            "attributes": body.attributes,
            "evidence_manifest_sha256": body.evidence_manifest_sha256,
            "policy_decision_sha256": body.policy_decision_sha256,
            "outcome_receipt_sha256": body.outcome_receipt_sha256,
        }
        lineage_sha = _hash(lineage)
        now = int(time.time())
        with self.engine.connect() as connection:
            existing = connection.execute(text(
                "SELECT lineage_sha256 FROM trace_spans_v21 WHERE workspace_id=:w AND trace_id=:trace AND span_id=:span"
            ), {"w": workspace_id, "trace": body.trace_id, "span": body.span_id}).first()
        if existing is not None:
            if str(existing[0]) != lineage_sha:
                raise ValueError("trace_span_conflict")
            return TraceSpanRecord(
                trace_id=body.trace_id, span_id=body.span_id, parent_span_id=body.parent_span_id,
                name=body.name, kind=body.kind, status=body.status,
                duration_ms=round((body.end_time_unix_nano - body.start_time_unix_nano) / 1_000_000, 6),
                lineage_sha256=lineage_sha, evidence_manifest_sha256=body.evidence_manifest_sha256,
                policy_decision_sha256=body.policy_decision_sha256, outcome_receipt_sha256=body.outcome_receipt_sha256,
            )
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO trace_spans_v21(
                workspace_id,trace_id,span_id,parent_span_id,name,kind,start_ns,end_ns,status,attributes_json,
                evidence_manifest_sha256,policy_decision_sha256,outcome_receipt_sha256,lineage_sha256,created_at
                ) VALUES(:w,:trace,:span,:parent,:name,:kind,:start,:end,:status,:attributes,:evidence,:policy,:receipt,:lineage,:created)"""
            ), {
                "w": workspace_id, "trace": body.trace_id, "span": body.span_id, "parent": body.parent_span_id,
                "name": body.name, "kind": body.kind, "start": body.start_time_unix_nano, "end": body.end_time_unix_nano,
                "status": body.status,
                "attributes": VAULT.encrypt_json(body.attributes, workspace_id=workspace_id, purpose="trace-attributes-v21"),
                "evidence": body.evidence_manifest_sha256, "policy": body.policy_decision_sha256,
                "receipt": body.outcome_receipt_sha256, "lineage": lineage_sha, "created": now,
            })
        return TraceSpanRecord(
            trace_id=body.trace_id, span_id=body.span_id, parent_span_id=body.parent_span_id,
            name=body.name, kind=body.kind, status=body.status,
            duration_ms=round((body.end_time_unix_nano - body.start_time_unix_nano) / 1_000_000, 6),
            lineage_sha256=lineage_sha, evidence_manifest_sha256=body.evidence_manifest_sha256,
            policy_decision_sha256=body.policy_decision_sha256, outcome_receipt_sha256=body.outcome_receipt_sha256,
        )

    def lineage(self, workspace_id: str, trace_id: str) -> TraceLineage:
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """SELECT span_id,lineage_sha256,evidence_manifest_sha256,policy_decision_sha256,outcome_receipt_sha256
                FROM trace_spans_v21 WHERE workspace_id=:w AND trace_id=:trace ORDER BY start_ns,span_id"""
            ), {"w": workspace_id, "trace": trace_id}).mappings().all()
        if not rows:
            raise LookupError("trace_not_found")
        bound = sum(
            bool(row["evidence_manifest_sha256"] and row["policy_decision_sha256"] and row["outcome_receipt_sha256"])
            for row in rows
        )
        trace_sha = _hash([{"span_id": row["span_id"], "lineage_sha256": row["lineage_sha256"]} for row in rows])
        return TraceLineage(
            trace_id=trace_id, span_count=len(rows), bound_span_count=bound,
            cryptographic_chain_complete=bound == len(rows), trace_sha256=trace_sha,
        )


LAB_V21 = AssuranceLabV21()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", action),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **metadata},
    )


@router.post("/datasets", response_model=DatasetRecord)
def create_dataset(body: DatasetCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> DatasetRecord:
    try:
        result = LAB_V21.create_dataset(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v21_dataset_create", "CREATED", {"dataset_id": result.dataset_id})
    return result


@router.post("/datasets/{dataset_id}/versions", response_model=DatasetVersion)
def create_dataset_version(dataset_id: str, body: DatasetVersionCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> DatasetVersion:
    try:
        result = LAB_V21.create_dataset_version(principal.workspace_id, dataset_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(request, principal, "v21_dataset_version", "CREATED", {"dataset_id": dataset_id, "version_id": result.version_id, "sha256": result.sha256})
    return result


@router.get("/datasets/versions/{version_id}", response_model=DatasetVersionContent)
def get_dataset_version(version_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> DatasetVersionContent:
    result = LAB_V21.get_dataset_version(principal.workspace_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="dataset_version_not_found")
    return result


@router.post("/prompts", response_model=PromptVersion)
def create_prompt_version(body: PromptVersionCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PromptVersion:
    result = LAB_V21.create_prompt_version(principal.workspace_id, body)
    _audit(request, principal, "v21_prompt_version", "CREATED", {"prompt_id": result.prompt_id, "version_id": result.version_id, "sha256": result.sha256})
    return result


@router.get("/prompts/{version_id}", response_model=PromptVersionContent)
def get_prompt_version(version_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> PromptVersionContent:
    result = LAB_V21.get_prompt_version(principal.workspace_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="prompt_version_not_found")
    return result


@router.post("/experiments", response_model=ExperimentRecord)
def create_experiment(body: ExperimentCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> ExperimentRecord:
    try:
        result = LAB_V21.create_experiment(principal.workspace_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(request, principal, "v21_experiment_create", "OPEN", {"experiment_id": result.experiment_id, "frozen_input_sha256": result.frozen_input_sha256})
    return result


@router.post("/experiments/{experiment_id}/results", response_model=ExperimentSummary)
def submit_experiment_results(experiment_id: str, body: ExperimentResultsSubmit, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> ExperimentSummary:
    try:
        result = LAB_V21.submit_results(principal.workspace_id, experiment_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v21_experiment_results", result.status, {"experiment_id": experiment_id, "summary_sha256": result.summary_sha256})
    return result


@router.get("/experiments/{experiment_id}", response_model=ExperimentSummary)
def get_experiment_summary(experiment_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ExperimentSummary:
    try:
        return LAB_V21.summary(principal.workspace_id, experiment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/experiments/compare", response_model=ExperimentComparison)
def compare_experiments(body: ExperimentComparisonRequest, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ExperimentComparison:
    try:
        result = LAB_V21.compare(principal.workspace_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v21_experiment_compare", "PASS" if result.passed else "FAIL", {"comparison_sha256": result.comparison_sha256, "primary_metric": result.primary_metric})
    return result


@router.post("/traces/spans", response_model=TraceSpanRecord)
def ingest_trace_span(body: TraceSpanIngest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> TraceSpanRecord:
    try:
        result = LAB_V21.ingest_span(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v21_trace_span", "RECORDED", {"trace_id": result.trace_id, "span_id": result.span_id, "lineage_sha256": result.lineage_sha256})
    return result


@router.get("/traces/{trace_id}/lineage", response_model=TraceLineage)
def verify_trace_lineage(trace_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> TraceLineage:
    if len(trace_id) != 32 or any(char not in "0123456789abcdef" for char in trace_id):
        raise HTTPException(status_code=422, detail="invalid_trace_id")
    try:
        return LAB_V21.lineage(principal.workspace_id, trace_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    return {
        "version": "v21",
        "workspace_id": principal.workspace_id,
        "versioned_datasets": True,
        "immutable_prompt_versions": True,
        "frozen_experiment_inputs": True,
        "experiment_score_comparison": True,
        "w3c_trace_context": True,
        "otlp_http_json_export": OTEL.enabled,
        "openinference_compatible_attributes": True,
        "trace_evidence_policy_receipt_binding": True,
        "encrypted_sensitive_payloads_at_rest": True,
        "unrestricted_model_execution_inside_assurance_lab": False,
        "automatic_permission_escalation": False,
        "live_agi_claim": False,
        "boundary": (
            "V21 closes core AI-engineering observability/evaluation gaps with versioned datasets, immutable prompts, "
            "reproducible experiment comparison and W3C/OTLP tracing while preserving ORBYTHRA evidence, policy and "
            "cryptographic outcome bindings. External product/security validation remains a separate gate."
        ),
    }
