from __future__ import annotations

import json
import zipfile
from pathlib import Path


def discover_openharmony_project(search_root: Path) -> dict[str, object]:
    root = Path(search_root)
    if not root.is_dir():
        return {
            "status": "missing",
            "quality_gate": "OPENHARMONY_PROJECT_MISSING",
            "search_root": str(root),
            "reason": f"search root does not exist: {root}",
        }

    project_dirs = sorted(
        {
            path.parent
            for path in root.rglob("hvigorw")
            if path.is_file() and not path.is_symlink() and _looks_like_openharmony_project(path.parent)
        },
        key=lambda item: item.as_posix(),
    )
    if not project_dirs:
        return {
            "status": "missing",
            "quality_gate": "OPENHARMONY_PROJECT_MISSING",
            "search_root": str(root),
            "reason": f"no hvigorw found under: {root}",
        }

    project_dir = _choose_project_dir(project_dirs)
    module_dirs = sorted({path.parent for path in project_dir.rglob("module.json5") if path.is_file() and not path.is_symlink()}, key=lambda item: item.as_posix())
    target_module_dir = _choose_module_dir(project_dir, module_dirs)
    package_dir, haps = _choose_package_dir(project_dir, target_module_dir)

    return {
        "status": "found",
        "quality_gate": "OPENHARMONY_PROJECT_DISCOVERED",
        "search_root": str(root),
        "project_dir": str(project_dir),
        "target_module_dir": str(target_module_dir) if target_module_dir is not None else None,
        "package_dir": str(package_dir) if package_dir is not None else None,
        "hap_count": len(haps),
        "hap_files": [str(hap) for hap in haps],
    }


def discover_hap_artifacts(search_root: Path) -> dict[str, object]:
    root = Path(search_root)
    if not root.is_dir():
        return {
            "status": "missing",
            "quality_gate": "HAP_ARTIFACTS_MISSING",
            "search_root": str(root),
            "reason": f"search root does not exist: {root}",
        }

    haps = sorted(
        [path for path in root.rglob("*.hap") if path.is_file() and not path.is_symlink()],
        key=lambda item: item.as_posix(),
    )
    if not haps:
        return {
            "status": "missing",
            "quality_gate": "HAP_ARTIFACTS_MISSING",
            "search_root": str(root),
            "reason": f"no .hap files found under: {root}",
            "hap_files": [],
        }

    test_haps = [hap for hap in haps if _is_test_hap(hap)]
    app_haps = [hap for hap in haps if not _is_test_hap(hap)]
    test_hap = _choose_hap(test_haps)
    app_hap = _choose_hap(app_haps)
    test_profile = inspect_hap_profile(test_hap) if test_hap is not None else {}
    package_dir = test_hap.parent if test_hap is not None else haps[0].parent
    return {
        "status": "found" if test_hap is not None else "incomplete",
        "quality_gate": "HAP_ARTIFACTS_DISCOVERED" if test_hap is not None else "HAP_TEST_ARTIFACT_MISSING",
        "search_root": str(root),
        "package_dir": str(package_dir),
        "hap_count": len(haps),
        "hap_files": [str(hap) for hap in haps],
        "app_hap": str(app_hap) if app_hap is not None else None,
        "test_hap": str(test_hap) if test_hap is not None else None,
        "test_bundle_name": test_profile.get("bundle_name"),
        "test_module_name": test_profile.get("module_name"),
    }


def inspect_hap_profile(hap_path: Path | None) -> dict[str, str]:
    if hap_path is None:
        return {}
    path = Path(hap_path)
    if not path.is_file() or path.suffix != ".hap" or path.is_symlink():
        return {}
    try:
        with zipfile.ZipFile(path) as hap:
            for name in ("module.json", "module.json5"):
                if name not in hap.namelist():
                    continue
                try:
                    profile = json.loads(hap.read(name).decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    return {}
                app = profile.get("app", {}) if isinstance(profile, dict) else {}
                module = profile.get("module", {}) if isinstance(profile, dict) else {}
                return {
                    "bundle_name": str(app.get("bundleName", "")) if isinstance(app, dict) and app.get("bundleName") else "",
                    "module_name": str(module.get("name", "")) if isinstance(module, dict) and module.get("name") else "",
                }
            if "pack.info" in hap.namelist():
                try:
                    return _profile_from_pack_info(json.loads(hap.read("pack.info").decode("utf-8", errors="replace")))
                except json.JSONDecodeError:
                    return {}
    except zipfile.BadZipFile:
        return {}
    return {}


def _profile_from_pack_info(profile: object) -> dict[str, str]:
    if not isinstance(profile, dict):
        return {}
    summary = profile.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    app = summary.get("app", {})
    app = app if isinstance(app, dict) else {}
    bundle_name = str(app.get("bundleName", "")) if app.get("bundleName") else ""

    module_name = ""
    packages = profile.get("packages", [])
    if isinstance(packages, list):
        for package in packages:
            if isinstance(package, dict) and package.get("moduleName"):
                module_name = str(package["moduleName"])
                break
            if isinstance(package, dict) and package.get("name"):
                module_name = str(package["name"])
                break
    if not module_name:
        modules = summary.get("modules", [])
        if isinstance(modules, list):
            for module in modules:
                if isinstance(module, dict) and module.get("name"):
                    module_name = str(module["name"])
                    break
                if isinstance(module, dict) and module.get("moduleName"):
                    module_name = str(module["moduleName"])
                    break
    return {"bundle_name": bundle_name, "module_name": module_name}


def _choose_project_dir(project_dirs: list[Path]) -> Path:
    with_haps = [item for item in project_dirs if any(item.rglob("*.hap"))]
    return with_haps[0] if with_haps else project_dirs[0]


def _looks_like_openharmony_project(project_dir: Path) -> bool:
    if (project_dir / "build-profile.json5").is_file():
        return True
    return any(path.is_file() and not path.is_symlink() for path in project_dir.rglob("module.json5"))


def _choose_module_dir(project_dir: Path, module_dirs: list[Path]) -> Path | None:
    if not module_dirs:
        return None
    with_haps = [item for item in module_dirs if any(item.rglob("*.hap"))]
    if with_haps:
        return with_haps[0]
    entry_modules = [item for item in module_dirs if item.name == "entry"]
    return entry_modules[0] if entry_modules else module_dirs[0]


def _choose_package_dir(project_dir: Path, target_module_dir: Path | None) -> tuple[Path | None, list[Path]]:
    roots = [target_module_dir, project_dir] if target_module_dir is not None else [project_dir]
    candidates: dict[Path, list[Path]] = {}
    seen: set[Path] = set()
    for root in roots:
        if root is None:
            continue
        for hap in sorted(root.rglob("*.hap"), key=lambda item: item.as_posix()):
            if hap.is_symlink():
                continue
            resolved = hap.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.setdefault(hap.parent, []).append(hap)
    if not candidates:
        return None, []
    ready_dirs = [
        (directory, haps)
        for directory, haps in candidates.items()
        if any(_is_test_hap(hap) for hap in haps) and any(not _is_test_hap(hap) for hap in haps)
    ]
    chosen_dir, haps = sorted(ready_dirs or list(candidates.items()), key=lambda item: (-len(item[1]), item[0].as_posix()))[0]
    return chosen_dir, haps


def _choose_hap(haps: list[Path]) -> Path | None:
    if not haps:
        return None
    return sorted(haps, key=lambda item: (len(item.parts), item.as_posix()))[0]


def _is_test_hap(path: Path) -> bool:
    name = path.name.lower()
    return "ohostest" in name or "test" in name
