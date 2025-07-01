import sys
sys.stdout.reconfigure(line_buffering=True)

import os
import re
import time
import json
import datetime
import requests
import re
import shutil
from pydub import AudioSegment
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
from tqdm import tqdm


# Load config
CONFIG_PATH = Path("/app/config.json")
if not CONFIG_PATH.exists():
    raise FileNotFoundError("Missing config.json file.")
config = json.loads(CONFIG_PATH.read_text())

KOKORO_ENDPOINT = config["api"]["host"] + config["api"]["endpoints"]["speech"]
TTS_SETTINGS = config.get("tts_settings", {})
MAX_RETRIES = config.get("max_retries", 5)
EPUB_DOCUMENT = 9
EPUB_IMAGE = 1

def main(): 
    convert_epubs_to_audiobooks()

def convert_epubs_to_audiobooks():
    current_folder = Path("/app/books")
    epub_files = list(current_folder.glob("*.epub"))

    if not epub_files:
        print("📁 No EPUB file found.")
        return

    for epub_file in epub_files:
        convert_epub_to_audiobook(epub_file)

def convert_epub_to_audiobook(epub_file: epub):
    start_time = datetime.datetime.now()
    current_folder = Path("/app/books")
    
    output_dir, timestamp = prepare_output_dir(current_folder, epub_file)

    print(f"📖 Processing: {epub_file.name}")
    print(f"📂 Output folder: {output_dir}")

    extract_cover_image(epub_file, output_dir)

    paragraphs = extract_paragraphs_from_epub(epub_file)
    content_json = output_dir / "content.json" 

    print("📝 Paragraphs extracted:")
    for para in paragraphs:
        para_id, text, is_chapter = para[:3]
        tag = "[CHAPTER]" if is_chapter else "[PARA]"
        print(f"{tag} {para_id}: {text[:80]}{'...' if len(text) > 80 else ''}")

    print(f"✏️ Converting {len(paragraphs)} paragraphs to audio parts...")

    total = len(paragraphs);
    remaining = total
    current = 0

    for paragraph in paragraphs:
        para_id = paragraph[0]
        text_content = paragraph[1]
        audio_file_prefix = f"adbk-{para_id}"

        is_chapter = paragraph[2] == 1
        chapter_title = paragraph[1] if is_chapter else ""

        if chapter_title:
            chapter_title = ' '.join(chapter_title.split()[:5])
            chapter_title = re.sub(r'[^A-Za-z0-9 ]+', '', chapter_title)
            chapter_title = chapter_title.replace(' ', '-')
            chapter_title = f"-{chapter_title}"
        else :
            None

        audio_file = f"{audio_file_prefix}{chapter_title}.mp3"
        paragraph[3] = audio_file

        audio_file_path = output_dir / audio_file

        if (audio_file_path.exists() and audio_file_path.stat().st_size > 0):
            print(f"✅ Audio file already exists: {audio_file}")
            remaining -= 1
            continue

        generate_audio_from_text(text_content, audio_file_path)
        
        current += 1
        elapsed_time = datetime.datetime.now() - start_time
        time_left = (elapsed_time / current) * (remaining - current)
        completed = total - remaining + current
        percent = round((completed / total) * 100)

        print(f"🔊 {audio_file} ({completed}/{total}) ({percent}%) - Elapsed: {elapsed_time} | Estimated time left: {time_left} | {remaining} at start")
        print("=" * os.get_terminal_size().columns)
        term_width = os.get_terminal_size().columns
        bar_length = term_width - 8  # Reserve space for " 100%" and brackets
        bar_length = max(10, bar_length)  # Ensure minimum bar length
        filled_length = int(bar_length * percent // 100)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"<{bar}> {percent}%")
        print("=" * os.get_terminal_size().columns)

    content_data = {
        "title": epub_file.stem,
        "created_at": timestamp,
        "paragraphs": paragraphs
    }

    content_json.write_text(json.dumps(content_data, indent=4, ensure_ascii=False))     

    if "--chapterize" in sys.argv:
        print("📚 Chapterizing MP3 files...")
        chapterize_mp3s(output_dir)

    print("🎉 Done!")

def prepare_output_dir(current_folder: Path, epub_file: epub.EpubBook) -> list:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = re.sub(r'[^A-Za-z0-9_.\- ]+', '', epub_file.stem)
    print(f"📂 Preparing output directory for: {base_name}")

    base_name = re.sub(r'[\s_]+', '-', base_name)
    base_name = re.sub(r'-{2,}', '-', base_name)  # Replace multiple dashes with a single dash
    base_name = base_name.strip('-')  # Remove leading/trailing dashes
    print(f"📂 Cleaned base name: {base_name}")

    output_dir = current_folder / base_name

    if output_dir.exists():
        mp3_files = list(output_dir.glob("*.mp3"))
        if mp3_files:
            # Sort by last modified time (most recent last)
            latest_mp3 = max(mp3_files, key=lambda f: f.stat().st_mtime)
            try:
                latest_mp3.unlink()
                print(f"🗑️ Deleted latest MP3: {latest_mp3.name}")
            except Exception as e:
                print(f"⚠️ Failed to delete {latest_mp3.name}: {e}")

    output_dir.mkdir(parents=True, exist_ok=True)
    return [output_dir, timestamp]

def is_valid_paragraph(text: str) -> bool:
    return re.search(r'[A-Za-z0-9.]', text)

def extract_paragraphs_from_epub(epub_path: Path) -> list:
    book = epub.read_epub(str(epub_path))
    paragraphs = []
    counter = 1

    for item in book.get_items():

        if item.get_type() == EPUB_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            chapter_title = soup.find(['h1', 'h2', 'h3'])
            if chapter_title and is_valid_paragraph(chapter_title.get_text()):
                para_id = f"pgrf-{counter:05d}"
                paragraphs.append([para_id, clean_text(chapter_title.get_text()), 1, ''])
                counter += 1
            for p in soup.find_all('p'):
                p_class = p.get('class', [])
                text = p.get_text().strip()
                is_chapter = 'chapter' in p_class or 'section' in p_class or re.search(r'chapter\s+\d+', text.lower()) is not None
                if text and is_valid_paragraph(text):
                    para_id = f"pgrf-{counter:05d}"
                    paragraphs.append([para_id, clean_text(text), 1 if is_chapter else 0, ''])
                    counter += 1
    return paragraphs

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
    #Replace all occurrences of keys in `replacements` with their corresponding values in the text.
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def fix_word_number_dash(text):
    # This pattern matches words followed by a dash and a number
    pattern = r'\b([A-Za-z]+)-(\d+)\b'
    # Replace with word space number
    return re.sub(pattern, r'\1 \2', text)

def generate_audio_from_text(text: str, output_path: Path):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            params = TTS_SETTINGS

            text = convert_all_caps_to_sentence_case(text)
            params.update({"input": text})

            word_count = len(text.split());

            if (word_count < 5):
                params.update({"speed": 0.9})

            if (word_count < 15): 
                params.update({"speed": 1.0})

            if (word_count >= 15):
                params.update({"speed": 1.1})

            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }

            print("\n" * 5)
            print(f"🔊 Sending request to Kokoro TTS: {KOKORO_ENDPOINT}")
            print(f"     voice: {params.get('voice', '')} | speed: {params.get('speed', '')} | input: {params.get('input', '')[:120]}")

            response = requests.post(KOKORO_ENDPOINT, json=params, headers=headers, timeout=300)
            response.raise_for_status()
            print(f"     📥 Response received: length={len(response.content)} bytes, type={response.headers.get('Content-Type', 'unknown')}")
            print(f"     💾 About to save audio file at {output_path.parent}...")
            #print("     📥 Raw response text:", response.text[:120])

            #result = response.json()
            #print(result)

            #print("🔊 Kokoro TTS response:")
            #print(json.dumps(result, indent=2, ensure_ascii=False))

            #if not result.get("success"):
            #    raise Exception("Kokoro TTS responded with success=False")

            #download_url = result["data"]["downloadUrl"]
            #audio_response = requests.get(download_url, timeout=10)
            #audio_response.raise_for_status()

            with open(output_path, 'wb') as f:
                f.write(response.content)

            print(f"✅ Audio saved: {output_path.name}")
            return

        except Exception as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                print("❌ Max retries reached. Skipping this paragraph.")
                #exit(1)  # Exit with error code
            wait_time = 5 * 2 ** (attempt - 1)
            print(f"⏳ Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

def convert_all_caps_to_sentence_case(text: str) -> str:
    def replacer(match):
        word = match.group(0)
        return word.capitalize()
    
    # Match words with ALL uppercase letters, minimum 2 characters (to avoid "I")
    return re.sub(r'\b[A-Z]{2,}\b', replacer, text)

def extract_cover_image(epub_path: Path, output_dir: Path) -> Path | None:
    book = epub.read_epub(str(epub_path))
    cover_image_path = output_dir / "cover.jpg"

    cover_image_item = None

    # Look for the item that is the cover
    for item in book.get_items():
        print(f"🔍 Checking item: {item.get_id()} ({item.get_type()})")
        if item.get_type() == EPUB_IMAGE:
            if cover_image_item == None:
                print("🔍 Found the first image in the book, using that as the cover if no other cover is found")
                cover_image_item = item
            
            if 'cover' in item.get_id().lower():
                print(f"🔍 Found specific cover image: {item.get_id()}")
                cover_image_item = item
                break
    if cover_image_item:
        with open(cover_image_path, 'wb') as f:
            f.write(item.get_content())
            print(f"🖼️ Saved cover image: {cover_image_path.name}")
            return cover_image_path

    print("❌ No cover image found in EPUB.")
    return None

def chapterize_mp3s(output_dir: Path):
    print("🔍 Scanning MP3 files to merge into chapters...")

    chapterized_dir = output_dir / output_dir.stem

    # 🔥 Delete existing chapterized folder
    if chapterized_dir.exists():
        print(f"🧹 Removing existing folder: {chapterized_dir}")
        shutil.rmtree(chapterized_dir)

    chapterized_dir.mkdir(parents=True, exist_ok=True)

    m4b_dir = chapterized_dir / "m4b"
    #m4b_dir.mkdir(parents=True, exist_ok=True)

    mp3_files = sorted(output_dir.glob("adbk-*.mp3"))
    chapters = []
    current_group = []
    current_chapter_name = None
    chapter_names = set()

    for mp3 in mp3_files:
        name = mp3.name
        print(f"🔍 Processing file: {name}")

        if '-' in name and re.search(r'pgrf-\d{5}-', name):
            # New chapter start
            if current_group:
                chapters.append((current_chapter_name, current_group))
                chapter_names.add(current_chapter_name)
            current_chapter_name = name
            current_group = [mp3]
        else:
            current_group.append(mp3)

    if current_group and current_chapter_name and current_chapter_name not in chapter_names:
        chapters.append((current_chapter_name, current_group))

    print(f"📚 Found {len(chapters)} chapters to merge.")
    print("Chapter names to merge:")
    for chapter_name, _ in chapters:
        print(f" - {chapter_name}")

    if not chapters:
        print("❌ No chapters found to merge. Nothing to do.")
        return
    
    print("🔗 About to merge chapters into single audio files...")

    merged_chapter_files = []

    for idx, (chapter_name, group) in enumerate(chapters):
        chapter_id = f"{idx+1:03d}"
        
        base_title = '-'.join(Path(chapter_name).stem.split('-')[3:]) if chapter_name else chapter_id
        base_title = re.sub(r'[^A-Za-z0-9\-]+', '', base_title)
        
        if base_title.isdigit():
            base_title = f"Chapter-{base_title}"
        
        out_filename = (f"{chapter_id}-{base_title}").upper()
        out_filename = f"{out_filename}.mp3"
        out_path = chapterized_dir / out_filename

        print(f"🔗 Merging {len(group)} files into: {out_filename}")
        ffmpeg_concat_mp3s(group, out_path)
        print(f"🎵 Saved: {out_filename} at {chapterized_dir}")

        merged_chapter_files.append(out_path)

    # 🖼️ Copy cover image if available
    cover_file = output_dir / "cover.jpg"
    if cover_file.exists():
        shutil.copy(cover_file, chapterized_dir / "cover.jpg")
        print("🖼️ Copied cover.jpg to chapterized/")

    # 🎧 Generate .m4b file
    if merged_chapter_files and False:
        m4b_output = m4b_dir / f"{output_dir.name}.m4b"
        concat_txt = output_dir / "concat_chapters.txt"
        with open(concat_txt, "w") as f:
            for chapter_file in merged_chapter_files:
                f.write(f"file '{chapter_file.absolute()}'\n")

        print(f"🎧 Generating M4B audiobook: {m4b_output.name}")

        ffmpeg_cmd = (
            f"ffmpeg -hide_banner -loglevel error -f concat -safe 0 -i \"{concat_txt}\" "
        )

        if cover_file.exists():
            ffmpeg_cmd += (
                f"-i \"{cover_file}\" -map 0:a -map 1:v -disposition:v:0 attached_pic "
            )
        else:
            ffmpeg_cmd += "-map 0:a "

        ffmpeg_cmd += (
            f"-vn -c:a aac -b:a 128k "
            f"\"{m4b_output}\""
        )

        result = os.system(ffmpeg_cmd)
        if result == 0:
            print(f"✅ M4B audiobook created: {m4b_output}")
        else:
            print(f"❌ Failed to generate M4B. Command was:\n{ffmpeg_cmd}")

def ffmpeg_concat_mp3s(mp3_files, output_path):
    list_file = output_path.with_suffix(".txt")
    with open(list_file, "w") as f:
        for mp3 in mp3_files:
            f.write(f"file '{mp3.resolve()}'\n")

    command = (
        f"ffmpeg -hide_banner -loglevel error -f concat -safe 0 -i \"{list_file}\" "
        f"-c copy \"{output_path}\""
    )

    result = os.system(command)
    if result == 0:
        print(f"🎵 Saved (ffmpeg): {output_path.name}")
    else:
        print(f"❌ FFmpeg concat failed for: {output_path.name}")

    list_file.unlink(missing_ok=True)  # Clean up the list file after use

#================================================================================================================

if __name__ == "__main__":
    main()
