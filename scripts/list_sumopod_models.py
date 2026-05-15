"""List models available on your Sumopod key. Run from coopilot/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from backend.config import get_sumopod_api_key, get_sumopod_base_url
    from openai import OpenAI

    client = OpenAI(api_key=get_sumopod_api_key(), base_url=get_sumopod_base_url())
    for m in sorted(client.models.list().data, key=lambda x: x.id):
        print(m.id)


if __name__ == "__main__":
    main()
