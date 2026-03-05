#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import yaml


# -------------------- Config --------------------

REPO_URL = "https://github.com/MathewLove17/apigeehybrid.git"
REVISION = "main"

ARGO_NAMESPACE = "argocd"
DEST_NAMESPACE = "apigee"
DEST_SERVER = "https://kubernetes.default.svc"
CREATE_NAMESPACE = False

ORGS_DIR_REL = Path("orgs")
APPS_DIR_REL = Path("apps")

OVERRIDES_DIR = "overrides"
OVERRIDES_PREFIX = "overrides_"
AUTOMATED = True

# Componentes globales pero generados "por org" para poder usar overrides por org
# (wave, shortName, chartPath, automated)
COMPONENTS_10_60: List[Tuple[str, str, str, bool]] = [
    ("10", "operator",        "charts/apigee-operator",        AUTOMATED),
    ("20", "datastore",       "charts/apigee-datastore",       AUTOMATED),
    ("30", "telemetry",       "charts/apigee-telemetry",       AUTOMATED),
    ("40", "redis",           "charts/apigee-redis",           AUTOMATED),
    ("50", "ingress-manager", "charts/apigee-ingress-manager", AUTOMATED),
    ("60", "org",             "charts/apigee-org",             AUTOMATED),
]

ENV_WAVE = "70"
ENV_CHART_PATH = "charts/apigee-env"

VHOST_WAVE = "80"
VHOST_CHART_PATH = "charts/apigee-virtualhost"



# -------------------- Helpers --------------------

def load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} no es un YAML tipo objeto (map).")
    return data


def dump_yaml(data: Dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def get_org_id(org_cfg: Dict[str, Any], org_file: Path) -> str:
    for key in ("org", "org_id", "name", "project_id"):
        v = org_cfg.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    raise ValueError(f"No encuentro org/org_id/name/project_id en {org_file}")


def get_charts_version(org_cfg: Dict[str, Any]) -> str:
    charts = org_cfg.get("charts")
    if isinstance(charts, dict):
        v = charts.get("version")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "unknown"


def override_valuefile_for(org_id: str, charts_ver: str) -> str:
    # Desde charts/* hacia overrides: ../../overrides/...
    return f"../../{OVERRIDES_DIR}/{OVERRIDES_PREFIX}{org_id}_v{charts_ver}.yaml"


def extract_env_names(org_cfg: Dict[str, Any]) -> List[str]:
    env_map = org_cfg.get("environments")
    if isinstance(env_map, dict):
        return [str(k) for k in env_map.keys()]
    if isinstance(env_map, list):
        out: List[str] = []
        for item in env_map:
            if isinstance(item, dict) and item.get("name"):
                out.append(str(item["name"]))
        return out

    # fallback si alguna org usa envs:
    envs = org_cfg.get("envs")
    if isinstance(envs, list):
        out2: List[str] = []
        for item in envs:
            if isinstance(item, dict) and item.get("name"):
                out2.append(str(item["name"]))
        return out2

    return []


def extract_envgroup_names(org_cfg: Dict[str, Any]) -> List[str]:
    eg = org_cfg.get("environment_groups")
    if isinstance(eg, dict):
        return [str(k) for k in eg.keys()]
    if isinstance(eg, list):
        out: List[str] = []
        for item in eg:
            if isinstance(item, dict) and item.get("name"):
                out.append(str(item["name"]))
        return out
    return []


def base_app(name: str, wave: str, chart_path: str, automated: bool) -> Dict[str, Any]:
    app: Dict[str, Any] = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": name,
            "namespace": ARGO_NAMESPACE,
            "annotations": {"argocd.argoproj.io/sync-wave": str(wave)},
        },
        "spec": {
            "project": "default",
            "source": {
                "repoURL": REPO_URL,
                "targetRevision": REVISION,
                "path": chart_path,
            },
            "destination": {"server": DEST_SERVER, "namespace": DEST_NAMESPACE},
            "syncPolicy": {
                "syncOptions": [f"CreateNamespace={'true' if CREATE_NAMESPACE else 'false'}", f"ServerSideApply=true" ],
            },
        },
    }

    if automated:
        app["spec"]["syncPolicy"]["automated"] = {"prune": False, "selfHeal": True}

    return app


def add_helm(app: Dict[str, Any], valuefile: str, parameters: Dict[str, str] | None) -> None:
    helm: Dict[str, Any] = {"valueFiles": [valuefile]}
    if parameters:
        helm["parameters"] = [{"name": k, "value": v} for k, v in parameters.items()]
    app["spec"]["source"]["helm"] = helm


def clean_generated_for_org(apps_dir: Path, org_id: str) -> None:
    # Borra todo lo generado para esa org (10–80) para evitar huérfanos
    for p in apps_dir.glob(f"apigee-*-*-{org_id}*.yaml"):
        p.unlink(missing_ok=True)


# -------------------- Main --------------------

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    orgs_dir = repo_root / ORGS_DIR_REL
    apps_dir = repo_root / APPS_DIR_REL
    apps_dir.mkdir(parents=True, exist_ok=True)

    changed = 0
    org_files = sorted(list(orgs_dir.glob("*.y*ml")))
    if not org_files:
        print(f"INFO: No hay ficheros YAML en {orgs_dir}")
        return

    for org_file in org_files:
        org_cfg = load_yaml(org_file)
        org_id = get_org_id(org_cfg, org_file)
        charts_ver = get_charts_version(org_cfg)

        valuefile = override_valuefile_for(org_id, charts_ver)

        # Limpieza para regenerar en limpio por org
        clean_generated_for_org(apps_dir, org_id)

        # 10–60 (por org)
        for wave, short, chart_path, automated in COMPONENTS_10_60:
            name = f"apigee-{wave}-{short}-{org_id}"
            app = base_app(name=name, wave=wave, chart_path=chart_path, automated=automated)
            add_helm(app, valuefile=valuefile, parameters=None)

            out = apps_dir / f"{name}.yaml"
            if write_if_changed(out, dump_yaml(app)):
                changed += 1
                print(f"OK: {out.name}")

        # 70 env (por org + env)
        for env in extract_env_names(org_cfg):
            name = f"apigee-{ENV_WAVE}-env-{org_id}-{env}"
            app = base_app(name=name, wave=ENV_WAVE, chart_path=ENV_CHART_PATH, automated=AUTOMATED)
            add_helm(app, valuefile=valuefile, parameters={"env": env})

            out = apps_dir / f"{name}.yaml"
            if write_if_changed(out, dump_yaml(app)):
                changed += 1
                print(f"OK: {out.name}")

        # 80 virtualhost (por org + envgroup)
        for eg in extract_envgroup_names(org_cfg):
            name = f"apigee-{VHOST_WAVE}-virtualhost-{org_id}-{eg}"
            app = base_app(name=name, wave=VHOST_WAVE, chart_path=VHOST_CHART_PATH, automated=AUTOMATED)
            add_helm(app, valuefile=valuefile, parameters={"envgroup": eg})

            out = apps_dir / f"{name}.yaml"
            if write_if_changed(out, dump_yaml(app)):
                changed += 1
                print(f"OK: {out.name}")

    print(f"Applications actualizadas: {changed}")


if __name__ == "__main__":
    main()