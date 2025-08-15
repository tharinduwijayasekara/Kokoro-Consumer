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

USE_EDGE_TTS = config.get("use_edge_tts_service", False)

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
            found_in_p_tag = None
            chapter_title = soup.find(['h1', 'h2', 'h3'])

            if chapter_title and is_valid_paragraph(chapter_title.get_text()):
                chapter_text = chapter_title.get_text()

            if chapter_text == '':
                [chapter_text, found_in_p_tag] = find_chapter_from_p_tags(soup)

            if chapter_text == '':
                chapter_text = f"Section {section_counter}"
                section_counter = section_counter + 1

            chapter_text_cleaned = clean_text(chapter_text)
            chapter_texts.append(chapter_text)

            para_id = f"pgrf-{counter:05d}"
            paragraphs.append([
                para_id, # id
                chapter_text_cleaned, # kokoro text
                1, # is chapter title
                '', # mp3 file name paragraph
                chapter_text, # display text
                0, # duration milliseconds
                0, # cumulative duration milliseconds,
                '' # mp3 file name chapter
            ])

            counter += 1

            for p in soup.find_all(['p', 'li', 'tr', 'dd', 'blockquote']):
                if found_in_p_tag and p == found_in_p_tag:
                    continue

                text = p.get_text().strip()
                if text and is_valid_paragraph(text):
                    para_id = f"pgrf-{counter:05d}"
                    italics_safe_text = extract_text_preserve_italics(p)
                    cleaned_text = clean_text(italics_safe_text)
                    if is_valid_paragraph(cleaned_text):
                        paragraphs.append([
                            para_id,
                            clean_text(italics_safe_text),
                            0,
                            '',
                            clean_text(italics_safe_text, True),
                            0,
                            0,
                            ''
                        ])
                        counter += 1

    counter += 1
    chapter_texts.append("Structure")

    para_id = f"pgrf-{counter:05d}"
    paragraphs.append([
        para_id,
        "Structure",
        1,
        '',
        "Structure",
        0,
        0,
        ''
    ])

    for item in book.get_items_of_type(EPUB_DOCUMENT):
        counter += 1
        para_id = f"pgrf-{counter:05d}"
        cleaned_text = clean_text(item.get_name())
        paragraphs.append([
            para_id,
            cleaned_text,
            0,
            '',
            cleaned_text,
            0,
            0,
            ''
        ])

    print("Chapters:", chapter_texts)
    return paragraphs


def find_chapter_from_p_tags(soup: BeautifulSoup) -> list:
    chapter_title = ''
    found_in_p_tag = None

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
            found_in_p_tag = p
            break

    return [chapter_title, found_in_p_tag]


def is_valid_paragraph(text: str) -> bool:
    return re.search(r'[A-Za-z0-9.]', text)


def clean_text(text: str, for_display: bool = False) -> str:
    text = text.strip()
    text = re.sub(r'\n+', '\n', text)  # Collapse multiple newlines into a single newline
    text = re.sub(r'\s+', ' ', text)  # Collapse all multiple spaces into a single space

    if not for_display:
        text = fix_word_number_dash(text)  # Fix word-number dash issues

        # Apply replacements from config if available
        replacements = config.get("replacements", {}) if (USE_EDGE_TTS == False) else config.get("replacements_edge_tts", {})
        if replacements:
            text = apply_replacements(text, replacements)

        text = re.sub(r'\s*\.(\s*\.)+\s*', '... ', text) # Collapse groups of any combo of multiple periods to one "..."
        text = re.sub(r'^\.\.\.\s', "", text) #Remove leading "... " from text

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

def extract_text_preserve_italics(p):
    parts = []
    detected = False

    def process_element(elem):
        nonlocal detected
        if isinstance(elem, NavigableString):
            parts.append(str(elem))
        elif isinstance(elem, Tag):
            # Check if this tag (and all its contents) are italic
            is_italic = (
                    elem.name in ['i', 'em'] or
                    (elem.name == 'span' and any('italic' in cls.lower() for cls in elem.get('class', []))) or
                    (elem.name == 'span' and any('class_s5fk' in cls.lower() for cls in elem.get('class', [])))
            )

            if is_italic:
                inner = elem.get_text()
                parts.append(f"*{inner}*")
                detected = True
            else:
                for child in elem.children:
                    process_element(child)

    process_element(p)

    processed = ''.join(parts).strip()

    if detected:
        print("Italics detected: ", p, parts, processed)

    return processed

def extract_text_with_italics(p):
    parts = []
    detected=False

    print("\n\n\n\n\n\nExtracting text from", p)

    for elem in p.descendants:

        print("Parts", parts)

        if isinstance(elem, NavigableString):
            last_part_idx = len(parts) - 1
            elem_string = str(elem)

            print("Element: ", elem_string)

            if last_part_idx < 0:
                print("Parts is empty, appending in the element string as is")
                parts.append(elem_string)
            if (last_part_idx >= 0
                    and (
                            parts[last_part_idx] != f"*{elem_string}*"
                            and parts[last_part_idx] != f"*{elem_string},*"
                            and parts[last_part_idx] != f"*{elem_string}.*"
                    )
            ):
                print("Parts is not empty, and last part is not: ", f"*{elem_string}*", f"*{elem_string},*", f"*{elem_string}.*")
                parts.append(elem_string)
        elif isinstance(elem, Tag):

            is_italic = (
                    elem.name in ['i', 'em'] or
                    (elem.name == 'span' and any('italic' in cls.lower() for cls in elem.get('class', []))) or
                    (elem.name == 'span' and any('class_s5fk' in cls.lower() for cls in elem.get('class', [])))
            )

            if is_italic:
                inner = elem.get_text()
                elem_string = str(elem)
                print("Part is in italics", [inner, elem_string])
                parts.append(f"*{inner}*")
                detected=True

    processed = ''.join(parts).strip()

    if detected:
        print("Italics detected: ", p, parts, processed)

    return processed