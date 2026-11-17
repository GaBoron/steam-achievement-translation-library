"""Package static website assets and verified Catalog V2 downloads."""
from __future__ import annotations

import json
import posixpath
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

from translation_artifacts import indexed_standalone
from urllib.parse import unquote, urlsplit

from catalog_v2 import schema_relative_path, translation_json_relative_path, validate_catalog
from steam_schema import load_schema, schema_languages, sha256, validate_schema_structure
from translation_json import render_translation
from steam_cover_images import parse_cover_images, refresh_cover_images, render_cover_images


ROOT = Path(__file__).resolve().parent.parent
RESERVED_PATHS = {"index-v2.json", "site-meta.json", ".nojekyll", "files"}
MODULE_REFERENCE_RE = re.compile(
    r"\b(?:import\s+(?:[^;\"']*?\s+from\s+)?|export\s+[^;\"']*?\s+from\s+)[\"']([^\"']+)[\"']"
    r"|\bimport\s*\(\s*[\"']([^\"']+)[\"']",
)


class _ResourceReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"script", "img"} and values.get("src"):
            self.references.append(values["src"])
        if tag == "link" and {"stylesheet", "icon"} & set((values.get("rel") or "").split()):
            if values.get("href"):
                self.references.append(values["href"])


def _source_file(root: Path, relative: PurePosixPath) -> Path:
    path = root.joinpath(*relative.parts)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Invalid website source file: {relative}")
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f"Website source must not contain symlinks: {relative}")
    return path


def _asset_payloads(root: Path) -> dict[PurePosixPath, bytes]:
    source = root / "web"
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Missing website source directory: web/")
    payloads: dict[PurePosixPath, bytes] = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Website asset must not be a symlink: {path.relative_to(root)}")
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(source).as_posix())
        if relative.parts[0] in RESERVED_PATHS:
            raise ValueError(f"Website asset conflicts with generated data: {relative}")
        payloads[relative] = _source_file(root, PurePosixPath("web") / relative).read_bytes()
    if PurePosixPath("index.html") not in payloads:
        raise ValueError("Missing website entry point: web/index.html")
    for relative, content in payloads.items():
        references: list[str] = []
        if relative.suffix == ".html":
            parser = _ResourceReferences()
            parser.feed(content.decode("utf-8"))
            references = parser.references
        elif relative.suffix == ".js":
            references = [
                match[0] or match[1]
                for match in MODULE_REFERENCE_RE.findall(content.decode("utf-8"))
            ]
        for reference in references:
            url = urlsplit(reference)
            if url.scheme or url.netloc or not url.path:
                continue
            path = unquote(url.path)
            if path.startswith("/"):
                raise ValueError(f"Use a relative asset URL for Pages subpaths: {relative}: {reference}")
            target = PurePosixPath(posixpath.normpath(str(relative.parent / path)))
            if ".." in target.parts or target not in payloads:
                raise ValueError(f"Missing local website asset: {relative}: {reference}")
    return payloads


def _catalog_payloads(root: Path) -> tuple[dict[PurePosixPath, bytes], int, int]:
    catalog_bytes = _source_file(root, PurePosixPath("index-v2.json")).read_bytes()
    catalog = validate_catalog(json.loads(catalog_bytes))
    payloads = {PurePosixPath("index-v2.json"): catalog_bytes}
    variants = 0
    for game_id, game in catalog["games"].items():
        for variant_id, variant in game["variants"].items():
            if variant.get("format") == "json":
                relative = PurePosixPath(translation_json_relative_path(game_id, variant_id))
                payloads[relative] = indexed_standalone(_source_file(root, relative), game_id, variant_id, variant)
                variants += 1
                continue
            relative = PurePosixPath(schema_relative_path(game_id, variant_id))
            path = _source_file(root, relative)
            binary, nodes = load_schema(path)
            rows = validate_schema_structure(binary, nodes)
            comparisons = {
                "size": (len(binary), variant["size"]),
                "SHA-256": (sha256(binary), variant["sha256"]),
                "languages": (schema_languages(nodes), variant["languages"]),
                "achievement count": (len(rows), variant["achievements"]),
            }
            for field, (actual, indexed) in comparisons.items():
                if actual != indexed:
                    raise ValueError(f"{relative}: {field} does not match Catalog V2")
            payloads[relative] = binary
            if "json" in variant:
                json_relative = PurePosixPath(translation_json_relative_path(game_id, variant_id))
                # Git's Windows checkout can expand canonical LF to CRLF.
                # Publish canonical UTF-8/LF JSON without modifying source files.
                content = _source_file(root, json_relative).read_text(encoding="utf-8").encode("utf-8")
                if len(content) != variant["json"]["size"]:
                    raise ValueError(f"{json_relative}: size does not match Catalog V2")
                expected = render_translation(game_id, variant_id, binary, nodes).encode("utf-8")
                if content != expected:
                    raise ValueError(f"{json_relative}: translation JSON does not match its source BIN")
                payloads[json_relative] = content
            variants += 1
    return payloads, len(catalog["games"]), variants


def _fresh_output(root: Path, output: Path) -> Path:
    output = output.expanduser().absolute()
    resolved = output.resolve()
    if output.is_symlink() or resolved == root or resolved in root.parents:
        raise ValueError(f"Refusing unsafe website output directory: {output}")
    if resolved.is_relative_to(root) and resolved.relative_to(root).parts[0] != "_site":
        raise ValueError("Website output inside the repository must be under _site/")
    if output.exists() and (not output.is_dir() or next(output.iterdir(), None) is not None):
        raise ValueError(f"Website output must be empty: {output}. Choose a fresh --output path or recycle it first.")
    return resolved


def build_site(output: Path, *, root: Path = ROOT, refresh_covers: bool = False) -> tuple[Path, int, int, int]:
    root = root.resolve(strict=True)
    target = _fresh_output(root, output)
    payloads = _asset_payloads(root)
    catalog_payloads, games, variants = _catalog_payloads(root)
    payloads.update(catalog_payloads)
    app_ids = json.loads(payloads[PurePosixPath("index-v2.json")])["games"]
    cover_path = PurePosixPath("steam-covers.json")
    covers = parse_cover_images(json.loads(payloads.get(cover_path, b"{}")), app_ids)
    if refresh_covers:
        covers = refresh_cover_images(app_ids, covers)
    payloads[cover_path] = render_cover_images(covers)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if len(revision) not in {40, 64} or any(character not in "0123456789abcdef" for character in revision):
        raise ValueError("Cannot determine the website's source commit")
    payloads[PurePosixPath("site-meta.json")] = (json.dumps({"revision": revision}) + "\n").encode("utf-8")
    payloads[PurePosixPath(".nojekyll")] = b""
    target.mkdir(parents=True, exist_ok=True)
    for relative, content in payloads.items():
        destination = target.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(content)
    return target, games, variants, sum(len(content) for content in payloads.values())
