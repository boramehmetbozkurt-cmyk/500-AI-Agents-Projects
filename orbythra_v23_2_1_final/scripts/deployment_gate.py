from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy" / "kubernetes" / "orbythra.yaml"


def _find(resources: list[dict], kind: str) -> dict:
    matches = [item for item in resources if item.get("kind") == kind]
    if not matches:
        raise SystemExit(f"missing Kubernetes resource kind: {kind}")
    return matches[0]


def main() -> None:
    resources = [item for item in yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")) if item]
    kinds = {str(item.get("kind")) for item in resources}
    required = {"ConfigMap", "Deployment", "Service", "PodDisruptionBudget", "HorizontalPodAutoscaler", "NetworkPolicy"}
    missing = sorted(required - kinds)
    if missing:
        raise SystemExit("missing Kubernetes resources: " + ", ".join(missing))
    if "Secret" in kinds:
        raise SystemExit("inline Kubernetes Secret objects are forbidden in the release manifest")

    config = _find(resources, "ConfigMap").get("data", {})
    if config.get("ORBYTHRA_ENV") != "production":
        raise SystemExit("ORBYTHRA_ENV must be production")
    if config.get("ORBYTHRA_KEY_MANAGEMENT_MODE") not in {"external_secret_manager", "kms_envelope"}:
        raise SystemExit("external key management mode is required")

    deployment = _find(resources, "Deployment")
    spec = deployment["spec"]
    if int(spec.get("replicas", 0)) < 2:
        raise SystemExit("production deployment requires at least two replicas")
    pod_spec = spec["template"]["spec"]
    if pod_spec.get("automountServiceAccountToken") is not False:
        raise SystemExit("service-account token automount must be disabled")
    if pod_spec.get("securityContext", {}).get("runAsNonRoot") is not True:
        raise SystemExit("pod runAsNonRoot is required")

    containers = pod_spec.get("containers", [])
    if len(containers) != 1:
        raise SystemExit("expected exactly one API container")
    container = containers[0]
    security = container.get("securityContext", {})
    if security.get("allowPrivilegeEscalation") is not False:
        raise SystemExit("allowPrivilegeEscalation must be false")
    if security.get("readOnlyRootFilesystem") is not True:
        raise SystemExit("readOnlyRootFilesystem must be true")
    if "ALL" not in security.get("capabilities", {}).get("drop", []):
        raise SystemExit("all Linux capabilities must be dropped")
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        if probe not in container:
            raise SystemExit(f"missing {probe}")
    resources_cfg = container.get("resources", {})
    if not resources_cfg.get("requests") or not resources_cfg.get("limits"):
        raise SystemExit("CPU/memory requests and limits are required")
    env_from = container.get("envFrom", [])
    if not any("secretRef" in item for item in env_from):
        raise SystemExit("external secretRef is required")
    if not any("configMapRef" in item for item in env_from):
        raise SystemExit("configMapRef is required")

    hpa = _find(resources, "HorizontalPodAutoscaler")
    if int(hpa["spec"].get("minReplicas", 0)) < 2:
        raise SystemExit("HPA minReplicas must be at least two")
    if int(hpa["spec"].get("maxReplicas", 0)) < int(hpa["spec"].get("minReplicas", 0)):
        raise SystemExit("HPA maxReplicas must not be below minReplicas")

    result = {
        "gate": "orbythra-production-deployment-v1",
        "status": "PASS",
        "resource_kinds": sorted(kinds),
        "replicas": int(spec["replicas"]),
        "external_key_management_mode": config["ORBYTHRA_KEY_MANAGEMENT_MODE"],
        "inline_secret_objects": 0,
        "security_context": "non-root/read-only/no-privilege-escalation/drop-all-capabilities",
        "probes": ["startup", "readiness", "liveness"],
        "validation_boundary": "Manifest configuration gate only; it does not prove that a live Kubernetes cluster is deployed or healthy.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
