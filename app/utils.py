from pathlib import Path

def get_folder_name(path: Path) -> str:
    print([
        path,
        path.parts,
        path.name
    ])

    return path.name