import json
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

BOOKS = [
    "MCAT Organic Chemistry Review 2026-2027 -- Kaplan Test Prep -- 2025 -- Kaplan Test Prep -- 2a9b7fa764f3068db1e0a88efdc6d2db -- Anna’s Archive.epub",
    "MCAT Behavioral Sciences Review 2026-2027 -- Alexander Stone Macnow (Ed) -- 2025 -- Kaplan Test Prep -- cb2ba481fac1c453f5c7d265181c3b66 -- Anna’s Archive.epub"
]

def build_cache():
    master_cache = {}
    for book_path in BOOKS:
        if not os.path.exists(book_path): continue
        book = epub.read_epub(book_path)
        book_title = book.get_metadata('DC', 'title')[0][0]
        master_cache[book_title] = {}

        # Scan all documents to find all practice sections
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content().decode('utf-8')
            if "Practice Questions" not in content and "Science Mastery" not in content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            chapter_name = soup.find(['h1', 'h2']).get_text().strip() if soup.find(['h1', 'h2']) else item.get_name()
            
            # Find the Answer Key for this specific section
            ans_key = []
            ans_header = soup.find(lambda t: t.name in ['h1', 'h2', 'p'] and "Answer Key" in t.text)
            if ans_header:
                ans_list = ans_header.find_next('ol')
                if ans_list:
                    ans_key = [li.get_text().strip()[0].upper() for li in ans_list.find_all('li')]

            # Extract all questions in the list-bold category
            questions = []
            main_list = soup.find('ol', class_='list-bold')
            if main_list:
                q_items = main_list.find_all('li', recursive=False)
                for i, li in enumerate(q_items):
                    nested_ol = li.find('ol')
                    if not nested_ol: continue
                    
                    options = [opt.get_text().strip() for opt in nested_ol.find_all('li')]
                    q_text = li.find(text=True, recursive=False) or li.get_text().split('A)')[0]
                    imgs = [img['src'].split('/')[-1] for img in li.find_all('img')]
                    
                    if q_text and options:
                        questions.append({
                            "question": str(q_text).strip(),
                            "options": options,
                            "answer": ans_key[i] if i < len(ans_key) else "A",
                            "image_list": imgs,
                            "book_path": book_path
                        })
            
            if questions:
                master_cache[book_title][chapter_name] = questions

    with open('localized_cache.json', 'w') as f:
        json.dump(master_cache, f, indent=4)
    print("New cache built with all found questions.")

if __name__ == "__main__":
    build_cache()