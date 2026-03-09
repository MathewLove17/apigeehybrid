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
 
# Si tus charts usan otros nombres de parámetros Helm, cambia esto
ENV_HELM_PARAM_NAME = "env"
ENVGROUP_HELM_PARAM_NAME = "envgroup"
 
# Si tus environment groups van con otro chart, cámbialo aquí
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
        raise ValueError(f"El fichero {path} no contiene un YAML válido.")
    return data
 
 
def find_single_org_file(repo_root: Path) -> Path:
    orgs_dir = repo_root / "orgs"
    if not orgs_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta {orgs_dir}")
 
    files = sorted(
        [p for p in orgs_dir.iterdir() if p.is_file() and p.suffix in {".yaml", ".yml"}]
    )
 
    if not files:
        raise FileNotFoundError(f"No hay ningún fichero YAML dentro de {orgs_dir}")
 
    if len(files) > 1:
        names = ", ".join(p.name for p in files)
        raise RuntimeError(
            f"En {orgs_dir} debe haber solo un fichero YAML de org. Hay varios: {names}"
        )
 
    return files[0]
 
 
def build_override_path(org_cfg: Dict[str, Any]) -> str:
    org_id = str(org_cfg["org_id"])
    version = str(org_cfg["charts"]["version"])
    return f"../../overrides/overrides_{org_id}_v{version}.yaml"
 
 
def build_elements(org_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    org_id = str(org_cfg["org_id"])
    value_file = build_override_path(org_cfg)
 
    elements: List[Dict[str, Any]] = []
 
    # Componentes base
    for stage, component_name, chart_path in BASE_COMPONENTS:
        elements.append(
            {
                "name": f"apigee-{stage}-{component_name}-{org_id}",
                "stage": stage,
                "path": chart_path,
                "namespace": DEST_NAMESPACE,
                "valueFile": value_file,
                "env": "",
                "envgroup": "",
            }
        )
 
    # Environment groups
    envgroups = org_cfg.get("environment_groups", {})
    for envgroup_name in envgroups.keys():
        elements.append(
            {
                "name": f"apigee-70-envgroup-{org_id}-{envgroup_name}",
                "stage": "70",
                "path": ENVGROUP_CHART_PATH,
                "namespace": DEST_NAMESPACE,
                "valueFile": value_file,
                "env": "",
                "envgroup": str(envgroup_name),
            }
        )
 
    # Environments
    environments = org_cfg.get("environments", {})
    for env_name in environments.keys():
        elements.append(
            {
                "name": f"apigee-80-env-{org_id}-{env_name}",
                "stage": "80",
                "path": "charts/apigee-env",
                "namespace": DEST_NAMESPACE,
                "valueFile": value_file,
                "env": str(env_name),
                "envgroup": "",
            }
        )
 
    return elements
 
 
def build_rolling_steps(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stages = sorted({str(e["stage"]) for e in elements}, key=lambda x: int(x))
    steps: List[Dict[str, Any]] = []
 
    for stage in stages:
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
    elements = build_elements(org_cfg)
 
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {
            "name": f"apigee-platform-{org_id}",
            "namespace": ARGO_NAMESPACE,
        },
        "spec": {
            "generators": [
                {
                    "list": {
                        "elements": elements,
                    }
                }
            ],
            "strategy": {
                "type": "RollingSync",
                "rollingSync": {
                    "steps": build_rolling_steps(elements),
                },
            },
            "template": {
                "metadata": {
                    "name": "{{name}}",
                    "namespace": ARGO_NAMESPACE,
                    "labels": {
                        "stage": "{{stage}}",
                    },
                },
                "spec": {
                    "project": "default",
                    "source": {
                        "repoURL": REPO_URL,
                        "targetRevision": REVISION,
                        "path": "{{path}}",
                        "helm": {
                            "valueFiles": [
                                "{{valueFile}}",
                            ],
                            "parameters": [
                                {
                                    "name": ENV_HELM_PARAM_NAME,
                                    "value": "{{env}}",
                                },
                                {
                                    "name": ENVGROUP_HELM_PARAM_NAME,
                                    "value": "{{envgroup}}",
                                },
                            ],
                        },
                    },
                    "destination": {
                        "server": DEST_SERVER,
                        "namespace": "{{namespace}}",
                    },
                    "syncPolicy": {
                        "syncOptions": [
                            "CreateNamespace=false",
                            "ServerSideApply=true",
                        ]
                    },
                },
            },
        },
    }
 
 
def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    org_file = find_single_org_file(repo_root)
    org_cfg = load_yaml(org_file)
 
    appset = build_applicationset(org_cfg)
 
    output_path = repo_root / "apps" / "applicationset.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
 
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            appset,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
 
    print(f"Org leída desde: {org_file}")
    print(f"ApplicationSet generado en: {output_path}")
 
 
if __name__ == "__main__":
    main()

 