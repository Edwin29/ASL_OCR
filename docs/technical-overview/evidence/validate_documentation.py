"""Read-only validation of overview artifacts and frozen product baseline."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

root = Path(__file__).resolve().parents[3]
analysis = root / "docs/technical-overview"
document = root / "docs/ASL_OCR_TECHNICAL_OVERVIEW.md"
baseline = json.loads((analysis / "baseline.json").read_text(encoding="utf-8-sig"))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
changed = [r["path"] for r in baseline["files"] if sha(root / r["path"]) != r["sha256"]]
targets = [document, analysis / "PASS_6_VERIFICATION_REPORT.md", analysis / "README.md"]
links = []
errors = []
for path in targets:
    content = path.read_text(encoding="utf-8-sig")
    for dest in re.findall(r"\[[^\]\n]+\]\(([^)]+)\)", content):
        if re.match(r"(?:https?://|#)", dest):
            continue
        base, _, anchor = dest.strip("<>").partition("#")
        target = (path.parent / base).resolve()
        entry = {"from": str(path.relative_to(root)), "target": dest}
        links.append(entry)
        if not target.is_file():
            errors.append({**entry, "error": "target missing"})
        elif re.fullmatch(r"L\d+", anchor):
            if int(anchor[1:]) > len(target.read_text(encoding="utf-8-sig").splitlines()):
                errors.append({**entry, "error": "source line out of range"})
text = document.read_text(encoding="utf-8-sig")
diagrams = re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)
result = {
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "source_files_checked": len(baseline["files"]),
    "source_hash_changes": changed,
    "local_links_checked": len(links),
    "link_errors": errors,
    "numbered_main_sections": re.findall(r"^## (\d+)\.", text, flags=re.M),
    "mermaid_count": len(diagrams),
    "mermaid_types": [d.splitlines()[0] for d in diagrams],
    "mermaid_renderer_executed": False,
    "code_fences_balanced": len(re.findall(r"^```", text, flags=re.M)) % 2 == 0,
    "unexpected_japanese_kana": bool(re.search(r"[\u3040-\u30ff]", text)),
    "document_sha256": sha(document),
}
result["passed"] = (
    not changed and not errors and result["head"] == baseline["head"]
    and result["numbered_main_sections"] == [str(n) for n in range(1, 10)]
    and len(diagrams) == 4 and result["code_fences_balanced"]
    and not result["unexpected_japanese_kana"]
)
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["passed"] else 1)
