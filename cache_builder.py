import json
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

# List of books to parse
BOOKS = [
    "MCAT Organic Chemistry Review 2026-2027 -- Kaplan Test Prep -- 2025 -- Kaplan Test Prep -- 2a9b7fa764f3068db1e0a88efdc6d2db -- Anna’s Archive.epub",
    "MCAT Behavioral Sciences Review 2026-2027 -- Alexander Stone Macnow (Ed) -- 2025 -- Kaplan Test Prep -- cb2ba481fac1c453f5c7d265181c3b66 -- Anna’s Archive.epub"
]

def build_cache():
    master_cache = {}

    for book_path in BOOKS:
        if not os.path.exists(book_path):
            print(f"Skipping: {book_path} (File not found)")
            continue
            
        print(f"Parsing {book_path}...")
        book = epub.read_epub(book_path)
        book_title = book.get_metadata('DC', 'title')[0][0]
        master_cache[book_title] = {}

        # Iterate through items in the EPUB to find practice sections
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), 'lxml')
            
            # Identify Chapter Title
            chapter_tag = soup.find(['h1', 'h2'], class_='chapter-title')
            if not chapter_tag: continue
            chapter_name = chapter_tag.get_text().strip()
            
            # Find Question Blocks (usually in a list or div with specific classes)
            questions = []
            q_blocks = soup.find_all('div', class_='question-block') # Example class
            
            for q in q_blocks:
                text = q.find('p', class_='question-text').get_text()
                options = [opt.get_text() for opt in q.find_all('li', class_='option')]
                ans = q.get('data-answer') # Kaplan often stores answer in metadata or key
                
                questions.append({
                    "question": text,
                    "options": options,
                    "answer": ans,
                    "book": book_title
                })
            
            if questions:
                master_cache[book_title][chapter_name] = questions

    # Save everything to a JSON file
    with open('quiz_cache.json', 'w') as f:
        json.dump(master_cache, f, indent=4)
    print("Cache successfully built!")

if __name__ == "__main__":
    build_cache()