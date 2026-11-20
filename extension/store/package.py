"""Build the Chrome Web Store upload: only the files the extension runs on.

    python extension/store/package.py      ->  extension/store/imbroglio-<version>.zip

The README, its doc images and this store/ folder stay out of the package.
Refuses to build if the manifest asks for localhost (a development setting).
"""

import json
import zipfile
from pathlib import Path

EXT = Path(__file__).resolve().parent.parent
FILES = ["manifest.json", "background.js", "popup.html", "popup.css", "popup.js"]


def main() -> None:
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    hosts = manifest.get("host_permissions", [])
    if any("localhost" in h or "127.0.0.1" in h for h in hosts):
        raise SystemExit(f"manifest asks for a local host ({hosts}); remove it before packaging")
    files = FILES + sorted(f"icons/{p.name}" for p in (EXT / "icons").glob("*.png"))
    out = EXT / "store" / f"imbroglio-{manifest['version']}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(EXT / name, name)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB): {', '.join(files)}")


if __name__ == "__main__":
    main()
