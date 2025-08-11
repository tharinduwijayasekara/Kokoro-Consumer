import json
import sys
from pathlib import Path

def get_folder_name(path: Path) -> str:
    print([
        path,
        path.parts,
        path.name
    ])

    return path.name

def get_config() -> json:
    # Load config
    config_path = Path("/app/config.json")
    if not config_path.exists():
        raise FileNotFoundError("Missing config.json file.")
    config = json.loads(config_path.read_text())

    if "--use_edge_tts" in sys.argv:
        config.update({"use_edge_tts_service": True})

    return config