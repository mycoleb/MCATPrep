import argparse
import json
import os
import re
import zipfile
from collections import defaultdict
from html import unescape
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, Tag


DEFAULT_BOOKS = [
    "MCAT Organic Chemistry Review 2026-2027 -- Kaplan Test Prep -- 2025 -- Kaplan Test Prep -- 2a9b7fa764f3068db1e0a88efdc6d2db -- Anna’s Archive.epub",
    "MCAT Behavioral Sciences Review 2026-2027 -- Alexander Stone Macnow (Ed) -- 2025 -- Kaplan Test Prep -- cb2ba481fac1c453f5c7d265181c3b66 -- Anna’s Archive.epub",
]


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
    raise RuntimeError("Could not locate OPF path from META-INF/container.xml")


def parse_opf(zf: zipfile.ZipFile, opf_path: str) -> Tuple[str, List[str]]:
    opf_xml = zf.read(opf_path)
    root = ET.fromstring(opf_xml)
    base_dir = os.path.dirname(opf_path)

    manifest = {}
    spine_ids = []

    for elem in root.iter():
        name = local_name(elem.tag)
        if name == "item":
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            media_type = elem.attrib.get("media-type", "")
            if item_id and href and "html" in media_type:
                full = os.path.normpath(os.path.join(base_dir, href)).replace("\\", "/")
                manifest[item_id] = full
        elif name == "itemref":
            idref = elem.attrib.get("idref")
            if idref:
                spine_ids.append(idref)

    spine_files = [manifest[i] for i in spine_ids if i in manifest]
    return base_dir, spine_files


def extract_page_num_from_pagebreak(tag: Tag) -> Optional[int]:
    for candidate in [
        tag.get("id", ""),
        tag.get("aria-label", ""),
        tag.get("title", ""),
        tag.get("epub:type", ""),
        tag.get_text(" ", strip=True),
    ]:
        m = re.search(r"page[_\s\-]*(\d+)", candidate, flags=re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"\bpage\s+(\d+)\b", candidate, flags=re.I)
        if m:
            return int(m.group(1))
    return None


def node_contains_pagebreak(node: Tag) -> bool:
    if not isinstance(node, Tag):
        return False
    if node.get("epub:type") == "pagebreak":
        return True
    if node.get("role") == "doc-pagebreak":
        return True
    if node.name == "span" and (
        "pagebreak" in (node.get("epub:type", "") or "").lower()
        or "doc-pagebreak" in (node.get("role", "") or "").lower()
    ):
        return True
    return False


def extract_images_from_node(node: Tag) -> List[Dict]:
    images = []
    if not isinstance(node, Tag):
        return images
    for img in node.find_all("img"):
        src = img.get("src", "")
        alt = clean_text(img.get("alt", ""))
        title = clean_text(img.get("title", ""))
        parent_text = ""
        if img.parent and isinstance(img.parent, Tag):
            parent_text = clean_text(img.parent.get_text(" ", strip=True))
        images.append(
            {
                "src": src,
                "file_name": os.path.basename(src) if src else "",
                "alt": alt,
                "title": title,
                "parent_tag": img.parent.name if img.parent and isinstance(img.parent, Tag) else "",
                "context_text": parent_text[:500],
            }
        )
    return images


def extract_bold_bits(node: Tag) -> List[str]:
    bits = []
    if not isinstance(node, Tag):
        return bits
    for tag in node.find_all(["b", "strong"]):
        txt = clean_text(tag.get_text(" ", strip=True))
        if txt:
            bits.append(txt)
    return bits


def classify_node(node: Tag) -> str:
    if not isinstance(node, Tag):
        return "other"
    name = node.name.lower()
    if re.fullmatch(r"h[1-6]", name):
        return "heading"
    if name in {"p", "blockquote"}:
        return "paragraph"
    if name in {"ol", "ul"}:
        return "list"
    if name in {"table"}:
        return "table"
    if name in {"figure", "img"}:
        return "figure"
    return "other"


def summarize_node(node: Tag) -> Optional[Dict]:
    if not isinstance(node, Tag):
        return None

    kind = classify_node(node)
    text = clean_text(node.get_text(" ", strip=True))
    images = extract_images_from_node(node)
    bold = extract_bold_bits(node)

    if not text and not images and kind == "other":
        return None

    summary = {
        "type": kind,
        "tag": node.name,
        "text": text[:1500],
        "bold_text": bold,
        "images": images,
    }

    if kind == "heading":
        summary["level"] = node.name.lower()

    if kind == "list":
        items = []
        for li in node.find_all("li", recursive=False):
            li_text = clean_text(li.get_text(" ", strip=True))
            if li_text:
                items.append(li_text[:500])
        summary["items"] = items[:20]

    if kind == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["th", "td"])]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells[:10])
        summary["rows_preview"] = rows[:10]

    return summary


def collect_page_chunks_from_html(html: str, file_name: str) -> List[Tuple[int, List[Dict]]]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup

    page_to_nodes: Dict[int, List[Dict]] = defaultdict(list)
    current_page: Optional[int] = None

    for node in body.descendants:
        if isinstance(node, NavigableString):
            continue
        if not isinstance(node, Tag):
            continue

        if node_contains_pagebreak(node):
            num = extract_page_num_from_pagebreak(node)
            if num is not None:
                current_page = num
            continue

        if current_page is None:
            continue

        parent = node.parent
        if isinstance(parent, Tag):
            # only summarize reasonably top-level content blocks
            if parent.name not in {"body", "section", "div", "article"}:
                continue

        summary = summarize_node(node)
        if not summary:
            continue

        summary["source_file"] = file_name
        page_to_nodes[current_page].append(summary)

    return sorted(page_to_nodes.items(), key=lambda x: x[0])


def analyze_epub_pages(epub_path: str, start_page: int, end_page: int) -> Dict:
    with zipfile.ZipFile(epub_path, "r") as zf:
        opf_path = parse_container_path(zf)
        _, spine_files = parse_opf(zf, opf_path)

        report = {
            "book": os.path.basename(epub_path),
            "page_range": [start_page, end_page],
            "pages": {},
        }

        for html_file in spine_files:
            if html_file not in zf.namelist():
                continue
            html = zf.read(html_file).decode("utf-8", errors="ignore")
            page_chunks = collect_page_chunks_from_html(html, html_file)

            for page_num, chunks in page_chunks:
                if start_page <= page_num <= end_page:
                    page_key = str(page_num)
                    if page_key not in report["pages"]:
                        report["pages"][page_key] = {
                            "headings": [],
                            "bold_text": [],
                            "images": [],
                            "paragraphs": [],
                            "lists": [],
                            "tables": [],
                            "other": [],
                        }

                    page_bucket = report["pages"][page_key]

                    for chunk in chunks:
                        chunk_type = chunk["type"]
                        if chunk_type == "heading":
                            page_bucket["headings"].append(
                                {
                                    "text": chunk.get("text", ""),
                                    "level": chunk.get("level", ""),
                                    "source_file": chunk.get("source_file", ""),
                                }
                            )
                        elif chunk_type == "paragraph":
                            if chunk.get("text"):
                                page_bucket["paragraphs"].append(
                                    {
                                        "text": chunk["text"],
                                        "source_file": chunk.get("source_file", ""),
                                    }
                                )
                        elif chunk_type == "list":
                            page_bucket["lists"].append(
                                {
                                    "items": chunk.get("items", []),
                                    "text": chunk.get("text", ""),
                                    "source_file": chunk.get("source_file", ""),
                                }
                            )
                        elif chunk_type == "table":
                            page_bucket["tables"].append(
                                {
                                    "rows_preview": chunk.get("rows_preview", []),
                                    "source_file": chunk.get("source_file", ""),
                                }
                            )
                        else:
                            if chunk.get("text") or chunk.get("images"):
                                page_bucket["other"].append(
                                    {
                                        "tag": chunk.get("tag", ""),
                                        "text": chunk.get("text", ""),
                                        "source_file": chunk.get("source_file", ""),
                                    }
                                )

                        for b in chunk.get("bold_text", []):
                            if b not in page_bucket["bold_text"]:
                                page_bucket["bold_text"].append(b)

                        for img in chunk.get("images", []):
                            page_bucket["images"].append(
                                {
                                    "file_name": img.get("file_name", ""),
                                    "src": img.get("src", ""),
                                    "alt": img.get("alt", ""),
                                    "title": img.get("title", ""),
                                    "parent_tag": img.get("parent_tag", ""),
                                    "context_text": img.get("context_text", ""),
                                    "source_file": chunk.get("source_file", ""),
                                }
                            )

        return report


def build_human_report(report: Dict) -> str:
    lines = []
    lines.append(f"BOOK: {report['book']}")
    lines.append(f"PAGE RANGE: {report['page_range'][0]}-{report['page_range'][1]}")
    lines.append("=" * 100)

    if not report["pages"]:
        lines.append("No content found for that page range.")
        return "\n".join(lines)

    for page_num in sorted(report["pages"], key=lambda x: int(x)):
        page = report["pages"][page_num]
        lines.append(f"\nPAGE {page_num}")
        lines.append("-" * 100)

        if page["headings"]:
            lines.append("HEADINGS:")
            for h in page["headings"]:
                lines.append(f"  - [{h['level']}] {h['text']}  (source: {h['source_file']})")

        if page["bold_text"]:
            lines.append("BOLD / STRONG TEXT:")
            for b in page["bold_text"]:
                lines.append(f"  - {b}")

        if page["images"]:
            lines.append("IMAGES:")
            for i, img in enumerate(page["images"], start=1):
                lines.append(f"  {i}. file_name: {img['file_name']}")
                lines.append(f"     src: {img['src']}")
                lines.append(f"     alt: {img['alt'] or '[none]'}")
                lines.append(f"     title: {img['title'] or '[none]'}")
                lines.append(f"     parent_tag: {img['parent_tag']}")
                lines.append(f"     context: {img['context_text'][:300] or '[none]'}")
                lines.append(f"     source: {img['source_file']}")

        if page["paragraphs"]:
            lines.append("PARAGRAPHS:")
            for p in page["paragraphs"][:12]:
                lines.append(f"  - {p['text'][:600]}  (source: {p['source_file']})")

        if page["lists"]:
            lines.append("LISTS:")
            for lst in page["lists"][:8]:
                if lst["items"]:
                    for item in lst["items"][:10]:
                        lines.append(f"  - {item}")
                elif lst["text"]:
                    lines.append(f"  - {lst['text'][:600]}")

        if page["tables"]:
            lines.append("TABLES:")
            for t in page["tables"]:
                for row in t["rows_preview"][:10]:
                    lines.append(f"  - {' | '.join(row)}")

        if page["other"]:
            lines.append("OTHER TAGGED CONTENT:")
            for other in page["other"][:10]:
                lines.append(
                    f"  - [{other['tag']}] {other['text'][:400]}  (source: {other['source_file']})"
                )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Deep EPUB page-range inspector")
    parser.add_argument("--start", type=int, default=33, help="Start page number")
    parser.add_argument("--end", type=int, default=45, help="End page number")
    parser.add_argument(
        "--books",
        nargs="*",
        default=DEFAULT_BOOKS,
        help="EPUB file paths to inspect",
    )
    parser.add_argument(
        "--output-dir",
        default="epub_debug_output",
        help="Directory where reports will be written",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    for book_path in args.books:
        if not os.path.exists(book_path):
            print(f"Skipping missing file: {book_path}")
            continue

        report = analyze_epub_pages(book_path, args.start, args.end)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(book_path))

        json_path = os.path.join(args.output_dir, f"{safe_name}.pages_{args.start}_{args.end}.json")
        txt_path = os.path.join(args.output_dir, f"{safe_name}.pages_{args.start}_{args.end}.txt")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(build_human_report(report))

        print(f"Wrote:\n  {json_path}\n  {txt_path}\n")


if __name__ == "__main__":
    main()
