import json
import os
import re
import zipfile
from html import unescape
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, Tag
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 

BOOKS = [
    os.path.join(BASE_DIR, f) 
    for f in os.listdir(BASE_DIR) 
    if f.endswith(".epub")
]

OUTPUT_FILE = "localized_cache.json"


def clean_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_container_path(zf: zipfile.ZipFile) -> str:
    container_xml = zf.read("META-INF/container.xml")
    root = ET.fromstring(container_xml)
    for elem in root.iter():
        if local_name(elem.tag) == "rootfile":
            full_path = elem.attrib.get("full-path")
            if full_path:
                return full_path
    raise RuntimeError("Could not find OPF path in META-INF/container.xml")


def parse_opf(zf: zipfile.ZipFile, opf_path: str) -> Tuple[str, List[str], str]:
    opf_xml = zf.read(opf_path)
    root = ET.fromstring(opf_xml)
    base_dir = os.path.dirname(opf_path)

    manifest = {}
    spine_ids = []
    title = os.path.basename(opf_path)

    for elem in root.iter():
        name = local_name(elem.tag)

        if name == "title" and elem.text and title == os.path.basename(opf_path):
            title = clean_text(elem.text)

        elif name == "item":
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            media_type = elem.attrib.get("media-type", "")
            if item_id and href:
                full_path = os.path.normpath(os.path.join(base_dir, href)).replace("\\", "/")
                manifest[item_id] = {
                    "href": full_path,
                    "media_type": media_type,
                }

        elif name == "itemref":
            idref = elem.attrib.get("idref")
            if idref:
                spine_ids.append(idref)

    spine_files = []
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if item and "html" in item["media_type"]:
            spine_files.append(item["href"])

    return base_dir, spine_files, title


def get_book_title_from_path(book_path: str, opf_title: str) -> str:
    if opf_title and opf_title.lower() != "content.opf":
        return opf_title
    stem = os.path.basename(book_path)
    if " -- " in stem:
        return stem.split(" -- ")[0]
    return stem

def find_shared_context(main_list: Tag) -> List[Tag]:
    """Finds tables or paragraphs immediately preceding the question list."""
    context_elements = []
    # Look at siblings appearing before the <ol>
    for sibling in main_list.find_previous_siblings():
        # Stop if we hit another section or a distant header
        if sibling.name in ["h1", "h2"]:
            break
        
        txt = sibling.get_text().lower()
        # Identify if this sibling contains the "Questions X and Y" trigger
        if "refer to the following" in txt or sibling.name == "table":
            context_elements.append(sibling)
            
    return context_elements[::-1] # Return in original document order
def get_heading_text(soup: BeautifulSoup) -> str:
    for tag_name in ["h1", "h2", "h3"]:
        tag = soup.find(tag_name)
        if tag:
            txt = clean_text(tag.get_text(" ", strip=True))
            if txt:
                return txt
    return ""


def find_answer_key(soup: BeautifulSoup) -> List[str]:
    ans_key = []

    ans_header = soup.find(
        lambda t: isinstance(t, Tag)
        and t.name in ["h1", "h2", "h3", "p", "div"]
        and "answer key" in clean_text(t.get_text(" ", strip=True)).lower()
    )
    if not ans_header:
        return ans_key

    ans_list = ans_header.find_next(["ol", "ul"])
    if not ans_list:
        return ans_key

    for li in ans_list.find_all("li", recursive=False):
        txt = clean_text(li.get_text(" ", strip=True))
        m = re.match(r"([A-D])\b", txt, flags=re.I)
        if m:
            ans_key.append(m.group(1).upper())
        elif txt:
            ans_key.append(txt[0].upper())

    return ans_key


def extract_image_names(node: Tag) -> List[str]:
    image_names = []
    for img in node.find_all("img"):
        src = img.get("src", "").strip()
        if src:
            image_names.append(os.path.basename(src))

    seen = set()
    out = []
    for name in image_names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out

def extract_options(answer_list: Tag) -> List[Dict]:
    options = []
    for option_li in answer_list.find_all("li", recursive=False):
        options.append(
            {
                "text": extract_option_text(option_li),
                # This makes sure images inside the <li> are captured
                "images": extract_image_names(option_li), 
            }
        )
    return options
def get_stem_text_before_answer_list(li: Tag, answer_list: Tag) -> str:
    parts = []

    roman_map = {
        1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
        6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"
    }

    for child in li.children:
        if child is answer_list:
            break

        if isinstance(child, NavigableString):
            txt = clean_text(str(child))
            if txt:
                parts.append(txt)
            continue

        if not isinstance(child, Tag):
            continue

        if child.name in ["ol", "ul"]:
            list_items = child.find_all("li", recursive=False)
            if list_items:
                rendered_items = []
                class_text = " ".join(child.get("class", [])).lower()

                for idx, item in enumerate(list_items, start=1):
                    item_text = clean_text(item.get_text(" ", strip=True))
                    if not item_text:
                        continue

                    if child.name == "ol" and "roman" in class_text:
                        rendered_items.append(f"{roman_map.get(idx, idx)}. {item_text}")
                    elif child.name == "ol":
                        rendered_items.append(f"{idx}. {item_text}")
                    else:
                        rendered_items.append(f"• {item_text}")

                if rendered_items:
                    parts.append("\n".join(rendered_items))
            continue

        txt = clean_text(child.get_text(" ", strip=True))
        if txt:
            parts.append(txt)

    return "\n\n".join(part for part in parts if part).strip()


def extract_option_text(option_li: Tag) -> str:
    txt = clean_text(option_li.get_text(" ", strip=True))
    txt = re.sub(r"^[A-D][\)\.\:]\s*", "", txt)
    return txt


def extract_options(answer_list: Tag) -> List[Dict]:
    options = []

    for option_li in answer_list.find_all("li", recursive=False):
        options.append(
            {
                "text": extract_option_text(option_li),
                "images": extract_image_names(option_li),
            }
        )

    return options


def choose_answer_list_from_question_li(li: Tag) -> Optional[Tag]:
    direct_lists = []

    for child in li.children:
        if isinstance(child, Tag) and child.name in ["ol", "ul"]:
            direct_items = child.find_all("li", recursive=False)
            if direct_items:
                direct_lists.append(child)

    if not direct_lists:
        return None

    scored = []
    for pos, lst in enumerate(direct_lists):
        items = lst.find_all("li", recursive=False)
        texts = [clean_text(x.get_text(" ", strip=True)) for x in items]

        score = 0

        if len(items) == 4:
            score += 10

        if any("only" in t.lower() for t in texts):
            score += 3

        if any(re.match(r"^[A-D][\)\.\:]\s*", t) for t in texts):
            score += 4

        score += pos  # later list gets slight preference
        scored.append((score, lst))

    scored.sort(key=lambda x: x[0])
    return scored[-1][1]


def extract_stem_images(li: Tag, answer_list: Tag) -> List[str]:
    image_names = []

    for child in li.children:
        if child is answer_list:
            break

        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue

        image_names.extend(extract_image_names(child))

    seen = set()
    out = []
    for name in image_names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def question_looks_real(question_text: str, options: List[Dict]) -> bool:
    if len(options) < 2:
        return False

    nonempty_options = [o for o in options if clean_text(o.get("text", "")) or o.get("images")]
    if len(nonempty_options) < 2:
        return False

    return bool(question_text)


def extract_questions_from_assessment_list(main_list: Tag) -> List[Tuple[str, List[Dict], List[str]]]:
    extracted = []

    for li in main_list.find_all("li", recursive=False):
        answer_list = choose_answer_list_from_question_li(li)
        if not answer_list:
            continue

        question_text = get_stem_text_before_answer_list(li, answer_list)
        stem_images = extract_stem_images(li, answer_list)
        options = extract_options(answer_list)

        if question_looks_real(question_text, options):
            extracted.append((question_text, options, stem_images))

    return extracted


def build_unique_section_key(item_name: str, display_heading: str) -> str:
    base = os.path.splitext(os.path.basename(item_name))[0]
    heading = clean_text(display_heading) or "Untitled Section"
    return f"{base} | {heading}"

def parse_book(book_path: str) -> Dict:
    with zipfile.ZipFile(book_path, "r") as zf:
        opf_path = parse_container_path(zf)
        _, spine_files, opf_title = parse_opf(zf, opf_path)
        book_title = get_book_title_from_path(book_path, opf_title)

        book_cache = {}
        # 
       
        for html_file in spine_files:
            if html_file not in zf.namelist():
                continue

            html = zf.read(html_file).decode("utf-8", errors="ignore")
            html_lc = html.lower()

            if (
                "science mastery assessment" not in html_lc
                and "practice questions" not in html_lc
                and "critical analysis and reasoning skills" not in html_lc
            ):
                continue

            soup = BeautifulSoup(html, "html.parser")
            heading = get_heading_text(soup)
            answer_key = find_answer_key(soup)

            main_list = soup.find("ol", class_=lambda c: c and "list-bold" in c)
            if not main_list:
                continue

            shared_context = find_shared_context(main_list)
            context_html = "".join([str(ctx) for ctx in shared_context])

            raw_questions = extract_questions_from_assessment_list(main_list)

            if not raw_questions:
                continue

            section_key = build_unique_section_key(html_file, heading)

            question_records = []
            for i, (question_text, options, stem_images) in enumerate(raw_questions, start=1):
                display_text = question_text
                if any(f" {i} " in ctx.get_text() or f"{i}," in ctx.get_text() for ctx in shared_context):
                    display_text = f"{context_html}\n\n{question_text}"

                question_records.append({
                    "question_number": i,
                    "question": display_text,
                    "options": options,
                    "answer": answer_key[i - 1] if i - 1 < len(answer_key) else "",
                    "image_list": stem_images,
                    "book_path": book_path,
                    "source_file": html_file,
                })

            book_cache[section_key] = question_records

        return {book_title: book_cache}


def main():
    master_cache = {}

    for book_path in BOOKS:
        if not os.path.exists(book_path):
            print(f"Skipping missing book: {book_path}")
            continue

        try:
            parsed = parse_book(book_path)
            master_cache.update(parsed)
            print(f"Parsed: {book_path}")
        except Exception as e:
            print(f"Failed parsing {book_path}: {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(master_cache, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()