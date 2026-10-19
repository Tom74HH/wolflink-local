"""Set actual repository metadata locally; no GitHub request or publication."""

import argparse
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(
        description="Configure your actual GitHub repository for HACS"
    )
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    url = args.repository.rstrip("/")
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", url):
        parser.error("Expected https://github.com/OWNER/REPOSITORY")
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components/wolflink_local/manifest.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data["documentation"] = url + "#readme"
    data["issue_tracker"] = url + "/issues"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("Repository links saved locally. No repository created or published.")


if __name__ == "__main__":
    main()
