"""Écrit le schéma OpenAPI de l'API dans le fichier donné, source des types du client frontend."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main(target: str) -> None:
    """Sérialise le schéma de façon stable : indentation fixe, caractères non ASCII conservés, saut de ligne final."""
    Path(target).write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
