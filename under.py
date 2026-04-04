import json
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

BOOKS = [
    "MCAT Organic Chemistry Review 2026-2027 -- Kaplan Test Prep -- 2025 -- Kaplan Test Prep -- 2a9b7fa764f3068db1e0a88efdc6d2db -- Anna’s Archive.epub",
    "MCAT Behavioral Sciences Review 2026-2027 -- Alexander Stone Macnow (Ed) -- 2025 -- Kaplan Test Prep -- cb2ba481fac1c453f5c7d265181c3b66 -- Anna’s Archive.epub"
]

def build_targeted_cache():
    cache = {}
    for book_path in BOOKS:
        book = epub.read_epub(book_path)
        title = book.get_metadata('DC', 'title')[0][0]
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        
        # Only process Sections 13 and 14 as requested
        book_data = []
        for i in [13, 14]:
            soup = BeautifulSoup(items[i].get_content(), 'xml')
            q_blocks = soup.find_all(['div', 'section'], class_=['question-block', 're-question'])
            
            for q in q_blocks:
                # Extract all images in this block into a list
                img_tags = q.find_all('img')
                images = [img['src'].split('/')[-1] for img in img_tags if img.get('src')]
                
                text = q.find(['p', 'div'], class_=['question-text', 'question-body'])
                options = [li.get_text().strip() for li in q.find_all('li')]
                
                if text and options:
                    book_data.append({
                        "question": text.get_text().strip(),
                        "options": options,
                        "answer": q.get('data-answer', 'A'),
                        "image_list": images, # Stored as a list for multi-image support
                        "book_path": book_path
                    })
        cache[title] = book_data

    with open('localized_cache.json', 'w') as f:
        json.dump(cache, f, indent=4)
    print("Localized Cache for Sections 13-14 created!")

if __name__ == "__main__":
    build_targeted_cache()