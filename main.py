from fastapi import FastAPI
from app.controller.book_controller import list_books as book_controller_list_books
from app.controller.book_controller import get_content as book_controller_get_content
app = FastAPI()

@app.get("/books/")
def list_books():
    return book_controller_list_books()

@app.get("/get-content/{file_path:path}")
def get_content(file_path: str):
    return book_controller_get_content(file_path)