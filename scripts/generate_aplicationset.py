#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml


REPO_URL = "https://github.com/MathewLove17/apigeehybrid.git"
REVISION = "main"
ARGO_NAMESPACE = "argocd"
DEST_SERVER = "https://kubernetes.default.svc"
DEST_NAMESPACE = "apigee"

# Cambia esto si tus charts usan otros nombres de parámetros Helm
ENV_HELM_PARAM_NAME = "env"
ENVGROUP_HELM_PARAM_NAME = "envgroup"

# Si el chart de los grupos de entorno no es este, cámbialo aquí
ENVGROUP_CHART_PATH = "charts/apigee-virtualhost"

BASE_COMPONENTS = [
    ("10", "operator", "charts/apigee-operator"),
    ("20", "datastore", "charts/apigee-datastore"),
    ("30", "telemetry", "charts/apigee-telemetry"),
    ("40", "redis", "charts/apigee-redis"),
    ("50", "ingress-manager", "charts/apigee-ingress-manager"),
    ("60", "org", "charts/apigee-org"),
]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"El fichero {path} no contiene un YAML válido de tipo objeto.")
    return data


def find_single_org_file(repo_root: Path) -> Path:
    orgs_dir = repo_root / "orgs"
    if not orgs_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta: {orgs_dir}")

    candidates = sorted(
        [p for p in orgs_dir.iterdir() if p.is_file() and p.suffix in {".yaml", ".yml"}]
    )

    if not candidates:
        raise FileNotFoundError(f"No hay ningún fichero YAML en {orgs_dir}")

    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise RuntimeError(
            f"Se esperaba un solo fichero en {orgs_dir}, pero hay varios: {names}"
        )

    return candidates[0]


def build_override_path(org_cfg: Dict[str, Any]) -> str:
    org_id = str(org_cfg["org_id"])
    version = str(org_cfg["charts"]["version"])
    return f"../../overrides/overrides_{org_id}_v{version}.yaml"


def build_core_elements(org_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    org_id = str(org_cfg["org_id"])
    value_file = build_override_path(org_cfg)

    elements: List[Dict[str, Any]] = []
    for stage, component_name, chart_path in BASE_COMPONENTS:
        elements.append(
            {
                "name": f"apigee-{stage}-{component_name}-{org_id}",
                "stage": stage,
                "path": chart_path,
                "namespace": DEST_NAMESPACE,
                "valueFile": value_file,
            }
        )
    return elements


def build_env_elements(org_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    org_id = str(org_cfg["org_id"])
    value_file = build_override_path(org_cfg)
    environments = org_cfg.get("environments", {})

    elements: List[Dict[str, Any]] = []
    for env_name in environments.keys():
        elements.append(
            {
                "name": f"apigee-70-env-{org_id}-{env_name}",
                "stage": "70",
                "path": "charts/apigee-env",
                "namespace": DEST_NAMESPACE,
                "valueFile": value_file,
                "env": str(env_name),
            }
        )
    return elements


def build_envgroup_elements(org_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    org_id = str(org_cfg["org_id"])
    value_file = build_override_path(org_cfg)
    envgroups = org_cfg.get("environment_groups", {})

    elements: List[Dict[str, Any]] = []
    for envgroup_name in envgroups.keys():
        elements.append(
            {
                "name": f"apigee-80-envgroup-{org_id}-{envgroup_name}",
                "stage": "80",
                "path": ENVGROUP_CHART_PATH,
                "namespace": DEST_NAMESPACE,
                "valueFile": value_file,
                "envgroup": str(envgroup_name),
            }
        )
    return elements


def build_rolling_steps(stages: List[str]) -> List[Dict[str, Any]]:
    unique_stages = sorted(set(stages), key=lambda x: int(x))
    steps: List[Dict[str, Any]] = []

    for stage in unique_stages:
        max_update: Any = 1
        if stage in {"70", "80"}:
            max_update = "100%"

        steps.append(
            {
                "matchExpressions": [
                    {
                        "key": "stage",
                        "operator": "In",
                        "values": [stage],
                    }
                ],
                "maxUpdate": max_update,
            }
        )

    return steps


def build_applicationset(org_cfg: Dict[str, Any]) -> Dict[str, Any]:
    org_id = str(org_cfg["org_id"])

    core_elements = build_core_elements(org_cfg)
    env_elements = build_env_elements(org_cfg)
    envgroup_elements = build_envgroup_elements(org_cfg)

    all_stages = [e["stage"] for e in core_elements + env_elements + envgroup_elements]

    generators: List[Dict[str, Any]] = []

    if core_elements:
        generators.append(
            {
                "list": {"elements": core_elements},
                "template": {
                    "metadata": {
                        "name": "{{.name}}",
                        "namespace": ARGO_NAMESPACE,
                        "labels": {"stage": "{{.stage}}"},
                    },
                    "spec": {
                        "project": "default",
                        "source": {
                            "repoURL": REPO_URL,
                            "targetRevision": REVISION,
                            "path": "{{.path}}",
                            "helm": {
                                "valueFiles": ["{{.valueFile}}"],
                            },
                        },
                        "destination": {
                            "server": DEST_SERVER,
                            "namespace": "{{.namespace}}",
                        },
                        "syncPolicy": {
                            "syncOptions": [
                                "CreateNamespace=false",
                                "ServerSideApply=true",
                            ]
                        },
                    },
                },
            }
        )

    if env_elements:
        generators.append(
            {
                "list": {"elements": env_elements},
                "template": {
                    "metadata": {
                        "name": "{{.name}}",
                        "namespace": ARGO_NAMESPACE,
                        "labels": {"stage": "{{.stage}}"},
                    },
                    "spec": {
                        "project": "default",
                        "source": {
                            "repoURL": REPO_URL,
                            "targetRevision": REVISION,
                            "path": "{{.path}}",
                            "helm": {
                                "valueFiles": ["{{.valueFile}}"],
                                "parameters": [
                                    {
                                        "name": ENV_HELM_PARAM_NAME,
                                        "value": "{{.env}}",
                                    }
                                ],
                            },
                        },
                        "destination": {
                            "server": DEST_SERVER,
                            "namespace": "{{.namespace}}",
                        },
                        "syncPolicy": {
                            "syncOptions": [
                                "CreateNamespace=false",
                                "ServerSideApply=true",
                            ]
                        },
                    },
                },
            }
        )

    if envgroup_elements:
        generators.append(
            {
                "list": {"elements": envgroup_elements},
                "template": {
                    "metadata": {
                        "name": "{{.name}}",
                        "namespace": ARGO_NAMESPACE,
                        "labels": {"stage": "{{.stage}}"},
                    },
                    "spec": {
                        "project": "default",
                        "source": {
                            "repoURL": REPO_URL,
                            "targetRevision": REVISION,
                            "path": "{{.path}}",
                            "helm": {
                                "valueFiles": ["{{.valueFile}}"],
                                "parameters": [
                                    {
                                        "name": ENVGROUP_HELM_PARAM_NAME,
                                        "value": "{{.envgroup}}",
                                    }
                                ],
                            },
                        },
                        "destination": {
                            "server": DEST_SERVER,
                            "namespace": "{{.namespace}}",
                        },
                        "syncPolicy": {
                            "syncOptions": [
                                "CreateNamespace=false",
                                "ServerSideApply=true",
                            ]
                        },
                    },
                },
            }
        )

    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {
            "name": f"apigee-platform-{org_id}",
            "namespace": ARGO_NAMESPACE,
        },
        "spec": {
            "generators": generators,
            "strategy": {
                "type": "RollingSync",
                "rollingSync": {
                    "steps": build_rolling_steps(all_stages),
                },
            },
        },
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    org_file = find_single_org_file(repo_root)
    org_cfg = load_yaml(org_file)

    output_file = repo_root / "apps" / "applicationset.yaml"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    appset = build_applicationset(org_cfg)

    with output_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            appset,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )

    print(f"Org leída desde: {org_file}")
    print(f"ApplicationSet generado en: {output_file}")


if __name__ == "__main__":
    main()