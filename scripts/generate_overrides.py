#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re

import yaml


# -------------------- Config --------------------

BASE_OVERRIDE_REL = Path("overrides") / "overrides_template.yaml"
ORGS_DIR_REL = Path("orgs")
OUT_DIR_REL = Path("overrides")

OUT_PREFIX = "overrides_"  # overrides/overrides_<org>_v<version>.yaml

COMPONENT_KEYS = [
    "cassandra",
    "ingressGateways",
    "envs",
    "virtualhosts",
    "mart",
    "connectAgent",
    "logger",
    "metrics",
]


# -------------------- YAML helpers --------------------

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


def lower_key_map(d: Dict[str, Any]) -> Dict[str, str]:
    return {str(k).lower(): str(k) for k in d.keys()}


def add_blank_lines_between_components(yaml_text: str) -> str:
    for k in COMPONENT_KEYS:
        yaml_text = re.sub(rf"\n({re.escape(k)}:)", r"\n\n\1", yaml_text)
    return yaml_text.lstrip("\n")


# -------------------- Extractors --------------------

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


def extract_env_names(org_cfg: Dict[str, Any]) -> List[str]:
    envs = org_cfg.get("envs")
    if isinstance(envs, list):
        out: List[str] = []
        for item in envs:
            if isinstance(item, dict) and item.get("name"):
                out.append(str(item["name"]))
        if out:
            return out

    env_map = org_cfg.get("environments")
    if isinstance(env_map, dict):
        return [str(k) for k in env_map.keys()]

    if isinstance(env_map, list):
        out2: List[str] = []
        for item in env_map:
            if isinstance(item, dict) and item.get("name"):
                out2.append(str(item["name"]))
        return out2

    return []


def extract_envgroups_with_fields(org_cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    eg = org_cfg.get("environment_groups")
    out: List[Dict[str, str]] = []

    if isinstance(eg, dict):
        for name, cfg in eg.items():
            d: Dict[str, str] = {"name": str(name)}
            if isinstance(cfg, dict):
                ing = cfg.get("ingressname")
                sec = cfg.get("sslSecret")
                if isinstance(ing, str) and ing.strip():
                    d["ingressname"] = ing.strip()
                if isinstance(sec, str) and sec.strip():
                    d["sslSecret"] = sec.strip()
            out.append(d)
        return out

    if isinstance(eg, list):
        for item in eg:
            if isinstance(item, dict) and item.get("name"):
                d2: Dict[str, str] = {"name": str(item["name"])}
                ing = item.get("ingressname")
                sec = item.get("sslSecret")
                if isinstance(ing, str) and ing.strip():
                    d2["ingressname"] = ing.strip()
                if isinstance(sec, str) and sec.strip():
                    d2["sslSecret"] = sec.strip()
                out.append(d2)
        return out

    return []


def extract_data_residency(org_cfg: Dict[str, Any]) -> Optional[Tuple[str, bool]]:
    keys = lower_key_map(org_cfg)
    dr_key = keys.get("dataresidency")
    if not dr_key:
        return None

    dr = org_cfg.get(dr_key)
    if not isinstance(dr, dict):
        return None

    enabled = bool(dr.get("enabled", False))
    cpl = dr.get("control_plane_location")
    if isinstance(cpl, str) and cpl.strip():
        return (cpl.strip(), enabled)

    return None


# -------------------- Builders (clonado de plantillas) --------------------

def build_envs_from_template(base_override: Dict[str, Any], env_names: List[str]) -> Optional[List[Dict[str, Any]]]:
    if not env_names:
        return None

    base_envs = base_override.get("envs")
    if not isinstance(base_envs, list) or not base_envs or not isinstance(base_envs[0], dict):
        raise ValueError("La plantilla base no tiene 'envs' como lista con al menos 1 elemento para clonar.")

    template = base_envs[0]
    out: List[Dict[str, Any]] = []
    for n in env_names:
        e = deepcopy(template)
        e["name"] = n
        out.append(e)
    return out


def build_vhosts_from_template(
    base_override: Dict[str, Any],
    envgroups: List[Dict[str, str]],
) -> Optional[List[Dict[str, Any]]]:
    if not envgroups:
        return None

    base_vh = base_override.get("virtualhosts")
    if not isinstance(base_vh, list) or not base_vh or not isinstance(base_vh[0], dict):
        raise ValueError("La plantilla base no tiene 'virtualhosts' como lista con al menos 1 elemento para clonar.")

    template = base_vh[0]
    out: List[Dict[str, Any]] = []

    for eg in envgroups:
        v = deepcopy(template)
        v["name"] = eg["name"]

        selector = v.get("selector")
        if not isinstance(selector, dict):
            selector = {}
            v["selector"] = selector

        if "ingressname" in eg:
            selector["ingress_name"] = eg["ingressname"]

        # aseguramos que no exista ingress_name fuera del selector
        v.pop("ingress_name", None)

        if "sslSecret" in eg:
            v["sslSecret"] = eg["sslSecret"]

        out.append(v)

    return out


# -------------------- Ordering helpers --------------------

def reorder_top_level_keys_with_contract_provider(out_override: Dict[str, Any]) -> Dict[str, Any]:
    if "contractProvider" not in out_override:
        return out_override

    new: Dict[str, Any] = {}
    inserted = False

    for k, v in out_override.items():
        new[k] = v
        if k == "httpProxy" and not inserted:
            new["contractProvider"] = out_override["contractProvider"]
            inserted = True

    if not inserted:
        cp = out_override["contractProvider"]
        new.pop("contractProvider", None)
        new["contractProvider"] = cp

    return new


# -------------------- Main generation --------------------

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    base_path = repo_root / BASE_OVERRIDE_REL
    orgs_dir = repo_root / ORGS_DIR_REL
    out_dir = repo_root / OUT_DIR_REL

    if not base_path.exists():
        raise SystemExit(f"ERROR: No existe plantilla base: {base_path}")
    if not orgs_dir.exists():
        raise SystemExit(f"ERROR: No existe directorio orgs: {orgs_dir}")

    base_override = load_yaml(base_path)

    changed = 0
    org_files = sorted(list(orgs_dir.glob("*.y*ml")))

    if not org_files:
        print(f"INFO: No hay ficheros YAML en {orgs_dir}")
        return

    for org_file in org_files:
        org_cfg = load_yaml(org_file)

        org_id = get_org_id(org_cfg, org_file)
        charts_ver = get_charts_version(org_cfg)

        env_names = extract_env_names(org_cfg)
        envgroups = extract_envgroups_with_fields(org_cfg)
        dr = extract_data_residency(org_cfg)

        out_override: Dict[str, Any] = deepcopy(base_override)

        # Copiar campos desde org si existen
        # AÑADIDO/ASEGURADO: k8sCluster se copia siempre si está en org_cfg
        copy_keys = [
            "instanceID",
            "namespace",
            "gcp",
            "k8sCluster",   # <-- tu nuevo cambio (ya estaba, pero aquí queda explícito)
            "org",
            "httpProxy",
            "enhanceProxyLimits",
            "securityContext",
            "istiod",
            "nodeSelector",
            "ingressGateways",
            "cassandra",
            "mart",
            "connectAgent",
            "logger",
            "metrics",
        ]
        for k in copy_keys:
            if k in org_cfg:
                out_override[k] = org_cfg[k]

        # envs
        new_envs = build_envs_from_template(base_override, env_names)
        if new_envs is not None:
            out_override["envs"] = new_envs

        # virtualhosts
        new_vhosts = build_vhosts_from_template(base_override, envgroups)
        if new_vhosts is not None:
            out_override["virtualhosts"] = new_vhosts

        # DataResidency -> contractProvider (o eliminarlo)
        if dr is not None:
            control_plane_location, enabled = dr
            if enabled:
                out_override["contractProvider"] = f"https://{control_plane_location}-apigee.googleapis.com"
            else:
                out_override.pop("contractProvider", None)
        else:
            out_override.pop("contractProvider", None)

        # contractProvider debajo de httpProxy
        out_override = reorder_top_level_keys_with_contract_provider(out_override)

        out_path = out_dir / f"{OUT_PREFIX}{org_id}_v{charts_ver}.yaml"

        content = dump_yaml(out_override)
        content = add_blank_lines_between_components(content)

        if write_if_changed(out_path, content):
            changed += 1
            print(
                f"OK: {out_path.name} | envs={len(env_names)} vhosts={len(envgroups)} dataResidency={dr}"
            )

    print(f"Overrides actualizados: {changed}")


if __name__ == "__main__":
    main()