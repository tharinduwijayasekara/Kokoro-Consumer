from starlette.responses import FileResponse

from app.utils import get_config
from pathlib import Path

config = get_config()
def list_books() -> list:
    current_folder = Path(config.get("books_folder"))
    folder_content = list(current_folder.glob("*"))
    items = []
    for item in folder_content:
        if item.is_file():
            continue
        items.append(get_book(item))

    return [items]

def get_book(book_path: Path):
    chapterized_path = book_path / book_path.name
    content_json_path = chapterized_path / 'content.json'
    cover_path = chapterized_path / 'cover.jpg'

    status = "invalid"
    if book_path.exists():
        status = "pending"
        if cover_path.exists() and content_json_path.exists():
            status = "completed"

    response_chapterized_path = f"{book_path.name}/{book_path.name}"
    response_content_json_path = f"{response_chapterized_path}/content.json"
    response_cover_path = f"{response_chapterized_path}/cover.jpg"

    return {
        "book_id": book_path.name,
        "chapterized_path": response_chapterized_path,
        "content_json_path": response_content_json_path,
        "cover_path": response_cover_path,
        "status": status
    }

def get_content(path: str):
    books_folder_str = config.get("books_folder")
    books_folder = Path(books_folder_str)
    full_path = books_folder / path

    try:
        full_path.relative_to(books_folder)
    except ValueError:
        return {"error": "invalid-path"}

    if not full_path.exists() or not full_path.is_file():
        return {"error": "no-such-file"}

    return FileResponse(full_path)