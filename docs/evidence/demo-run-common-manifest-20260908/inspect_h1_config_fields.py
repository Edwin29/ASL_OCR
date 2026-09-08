from pathlib import Path
import json
import tomllib

root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944\config")
result = {}
for path in sorted(root.glob("*.toml")):
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    def clean(value):
        if isinstance(value, dict):
            return {
                key: ("<configured>" if any(token in key.lower() for token in ("password", "api_key", "secret")) else clean(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    result[path.name] = clean(data)
print(json.dumps(result, ensure_ascii=False, indent=2))
