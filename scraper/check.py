"""Exit 1 if a distributor that had extracted values in the previous commit no longer has them."""
import json
import subprocess
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "tarifas.json"


def main():
    try:
        prev = json.loads(subprocess.run(["git", "show", "HEAD~1:site/data/tarifas.json"],
                                         capture_output=True, check=True, text=True).stdout)
    except subprocess.CalledProcessError:
        return 0
    cur = {e["id"]: e for e in json.loads(DATA.read_text())["distribuidoras"]}
    lost = [e["id"] for e in prev["distribuidoras"]
            if e["estado"] == "ok" and cur.get(e["id"], {}).get("estado") != "ok"]
    for i in lost:
        print(f"::warning::{i}: dejó de extraer valores ({cur.get(i, {}).get('intentos')})")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
