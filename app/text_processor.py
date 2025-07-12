import os
import re
import time
import json
import datetime
import requests
import re
import shutil

from ebooklib.epub import EpubBook, EpubItem
from pydub import AudioSegment
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag
from tqdm import tqdm

EPUB_DOCUMENT = 9

CONFIG_PATH = Path("/app/config.json")
if not CONFIG_PATH.exists():
    raise FileNotFoundError("Missing config.json file.")
config = json.loads(CONFIG_PATH.read_text())


def extract_paragraphs_from_epub(epub_path: Path) -> list:
    book = epub.read_epub(str(epub_path))
    paragraphs = []
    counter = 1
    section_counter = 1
    chapter_texts = []

    for item in book.get_items():

        if item.get_type() == EPUB_DOCUMENT:

            soup = BeautifulSoup(item.get_content(), 'html.parser')

            chapter_text = ''
            chapter_title = soup.find(['h1', 'h2', 'h3'])

            if chapter_title and is_valid_paragraph(chapter_title.get_text()):
                chapter_text = chapter_title.get_text()

            if chapter_text == '':
                chapter_text = find_chapter_from_p_tags(soup)

            if chapter_text == '':
                chapter_text = f"Section {section_counter}"
                section_counter = section_counter + 1

            chapter_text_cleaned = clean_text(chapter_text)
            chapter_texts.append(chapter_text)

            para_id = f"pgrf-{counter:05d}"
            paragraphs.append([
                para_id,
                chapter_text_cleaned,
                1,
                '',
                chapter_text,
                0,
                0
            ])

            counter += 1

            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text and is_valid_paragraph(text):
                    para_id = f"pgrf-{counter:05d}"
                    italics_safe_text = extract_text_with_italics(p)
                    paragraphs.append([
                        para_id,
                        clean_text(italics_safe_text),
                        0,
                        '',
                        italics_safe_text,
                        0,
                        0
                    ])
                    counter += 1

    print("Chapters:", chapter_texts)
    return paragraphs


def find_chapter_from_p_tags(soup: BeautifulSoup) -> str | None:
    chapter_title = ''

    for p in soup.find_all('p'):
        p_class = p.get('class', [])
        text = p.get_text().strip()
        is_chapter = ((
                'chapter' in p_class
                or 'section' in p_class
                or 'CT' in p_class
                or re.search(r'chapter\s+\d+', text.lower()) is not None)
                or re.search(r'[a-zA-Z]{2,}', text))

        if is_chapter:
            chapter_title = text
            break

    return chapter_title


def is_valid_paragraph(text: str) -> bool:
    return re.search(r'[A-Za-z0-9.]', text)


def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r'\n+', '\n', text)  # Collapse multiple newlines into a single newline
    text = re.sub(r'\s+', ' ', text)  # Collapse all multiple spaces into a single space

    text = fix_word_number_dash(text)  # Fix word-number dash issues

    # Apply replacements from config if available
    replacements = config.get("replacements", {})
    if replacements:
        text = apply_replacements(text, replacements)

    return text


def apply_replacements(text: str, replacements: dict) -> str:
    # Replace all occurrences of keys in `replacements` with their corresponding values in the text.
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def fix_word_number_dash(text):
    # This pattern matches words followed by a dash and a number
    pattern = r'\b([A-Za-z]+)-(\d+)\b'
    # Replace with word space number
    return re.sub(pattern, r'\1 \2', text)

def extract_text_with_italics(p):
    parts = []

    for elem in p.descendants:
        if isinstance(elem, NavigableString):
            parts.append(str(elem))
        elif isinstance(elem, Tag):
            is_italic = (
                    elem.name in ['i', 'em'] or
                    (elem.name == 'span' and any('italic' in cls.lower() for cls in elem.get('class', [])))
            )
            if is_italic:
                inner = elem.get_text()
                parts.append(f"*{inner}*")

    return ''.join(parts).strip()