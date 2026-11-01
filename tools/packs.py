"""Inspect, conservatively install, and reproducibly archive research packs. Never trade."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def framework_digest(path: Path) -> str:
    """Git's Windows CRLF checkout must match the reviewed Linux LF source."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text("utf-8"))


def pack_entry(slug: str) -> dict:
    for item in manifest()["packs"]:
        if item["slug"] == slug:
            return item
    raise ValueError(f"Unknown pack: {slug}")


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    return path


def pack_files(item: dict) -> list[Path]:
    base = contained(ROOT, "packs/" + item["slug"])
    required = [base / "docs" / name for name in
                ("STRATEGY.md", "TESTING.md", "VALIDATION.md", "RESEARCH.md")]
    required += [contained(base, item["strategy_file"]), contained(base, item["test_file"])]
    if not all(path.is_file() for path in required):
        raise ValueError(f"Incomplete package: {item['slug']}")
    return required


def install(slug: str, framework: Path) -> list[str]:
    item, info = pack_entry(slug), manifest()
    framework = framework.resolve()
    risk_base = framework / "user_data/strategies/framework_base.py"
    if not risk_base.is_file() or framework_digest(risk_base) != info["framework"]["base_sha256"]:
        raise ValueError("Target framework_base.py does not match the reviewed version; review compatibility first.")
    source_root = contained(ROOT, "packs/" + slug)
    writes = []
    for source in pack_files(item):
        relative = source.relative_to(source_root)
        destination = (contained(framework, "docs/trader_packs/" + slug + "/" + source.name)
                       if relative.parts[0] == "docs" else contained(framework, relative.as_posix()))
        if destination.exists():
            if not destination.is_file() or digest(source) != digest(destination):
                raise ValueError(f"Refusing to overwrite existing different file: {destination}")
        writes.append((source, destination))
    # Check ALL destinations before writing any file. No config or registry is copied.
    for source, destination in writes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
    return [str(destination) for _, destination in writes]


def build(slug: str, output: Path) -> dict:
    item = pack_entry(slug)
    base = ROOT / "packs" / slug
    files = pack_files(item)
    output.mkdir(parents=True, exist_ok=True)
    target = output / (slug + "-" + manifest().get("archive_version", "v2") + ".zip")
    payload = {path.relative_to(base).as_posix(): path.read_bytes() for path in files}
    payload["PACK.json"] = (json.dumps({"pack": item, "framework": manifest()["framework"]},
                                      ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payload["SHA256SUMS.txt"] = ("\n".join(
        hashlib.sha256(data).hexdigest() + "  " + name for name, data in sorted(payload.items())
    ) + "\n").encode("utf-8")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            entry = zipfile.ZipInfo(name, (2026, 11, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed")
    return {"pack": slug, "file": target.name, "sha256": digest(target), "bytes": target.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    ins = sub.add_parser("install")
    ins.add_argument("--pack", required=True)
    ins.add_argument("--framework", type=Path, required=True)
    arc = sub.add_parser("build")
    arc.add_argument("--pack", default="all")
    arc.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    if args.command == "list":
        result = manifest()
    elif args.command == "install":
        result = {"pack": args.pack, "files": install(args.pack, args.framework),
                  "note": "No strategy enabled. Configuration and idea registry unchanged."}
    else:
        selected = manifest()["packs"] if args.pack == "all" else [pack_entry(args.pack)]
        result = [build(item["slug"], args.out) for item in selected]
        (args.out / "archives.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
