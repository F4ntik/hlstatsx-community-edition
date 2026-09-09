"""Build install and non-destructive upgrade archives from an exact Git revision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "LICENSE", "CREATORS", "IMAGES"}
CONFIG_EXAMPLES = {"web/config.php", "scripts/hlstats.conf"}


def package_path(name: str, upgrade: bool) -> str | None:
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or (parts[0] not in {"web", "scripts", "sql", "heatmaps", "amxmodx", "sourcemod", "docs"} and name not in ROOT_FILES):
        return None
    if any(part in {"__pycache__", ".venv", "tests", ".pytest_cache", "cache", ".repowise", "node_modules", "target"} for part in parts):
        return None
    if name.startswith(("scripts/replay_baseline/", "docs/audits/", "docs/plans/", "scripts/GeoLiteCity/")):
        return None
    if name.startswith("scripts/") and (path.name.startswith(("tmp_", "test_")) or "smoke" in path.name or path.name == "heatmap_visual_gate.js"):
        return None
    # Local asset acquisition is not part of the runtime distribution.
    if name in {"scripts/heatmap_import_goldsrc.py", "scripts/heatmap_bsp_registration.py"}:
        return None
    if path.suffix.lower() in {".log", ".pyc", ".pyo", ".pkl", ".db", ".gz", ".tgz", ".zip"}:
        return None
    if name in CONFIG_EXAMPLES:
        return name + ".example"
    if upgrade:
        # An existing image and its DB calibration are one installation-owned pair.
        if name.startswith(("heatmaps/", "web/hlstatsimg/", "sql/install")):
            return None
    return name


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def build(output: Path, revision: str) -> dict:
    commit = git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
    entries = []
    for record in git("ls-tree", "-rz", commit).split(b"\0"):
        if not record:
            continue
        meta, raw_name = record.split(b"\t", 1)
        mode, kind, object_id = meta.decode().split()
        name = raw_name.decode("utf-8")
        if package_path(name, False) is None:
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Unsupported release entry: " + name)
        entries.append((name, mode, object_id))
    output.mkdir(parents=True, exist_ok=True)
    paths = {kind: output / f"hlstatsx_py-{commit[:12]}-{kind}.zip" for kind in ("install", "upgrade")}
    manifest_path = output / f"hlstatsx_py-{commit[:12]}-manifest.json"
    if any(p.exists() for p in [*paths.values(), manifest_path]):
        raise FileExistsError("Release output already exists; choose a fresh output directory")
    manifests = {kind: [] for kind in paths}
    archives = {kind: zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED, compresslevel=6) for kind, path in paths.items()}
    reader = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert reader.stdin is not None and reader.stdout is not None
    try:
        for name, mode, object_id in entries:
            reader.stdin.write((object_id + "\n").encode())
            reader.stdin.flush()
            header = reader.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                raise RuntimeError("Cannot read release blob: " + name)
            data = reader.stdout.read(int(header[2]))
            if reader.stdout.read(1) != b"\n" or len(data) != int(header[2]):
                raise RuntimeError("Incomplete release blob: " + name)
            for kind, archive in archives.items():
                destination = package_path(name, kind == "upgrade")
                if destination is None:
                    continue
                info = zipfile.ZipInfo(destination, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = int(mode, 8) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
                manifests[kind].append({"path": destination, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        reader.stdin.close()
        if reader.wait() != 0:
            raise RuntimeError("Git object reader failed")
    finally:
        for archive in archives.values():
            archive.close()
        if reader.poll() is None:
            reader.kill()
            reader.wait()
    receipt = {"commit": commit, "archives": {kind: {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "files": manifests[kind]} for kind, path in paths.items()}}
    manifest_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {"commit": commit, "manifest": str(manifest_path), "archives": {kind: {"path": str(path), "files": len(manifests[kind]), "bytes": path.stat().st_size} for kind, path in paths.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir.resolve(), args.revision), indent=2))
