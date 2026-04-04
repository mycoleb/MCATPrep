import json
import random
import os

def load_cache():
    if not os.path.exists('quiz_cache.json'):
        print("Error: No cache found. Run cache_builder.py first.")
        return None
    with open('quiz_cache.json', 'r') as f:
        return json.load(f)

def start_quiz():
    data = load_cache()
    if not data: return

    print("--- MCAT Master Quizzer ---")
    # Selection logic for Book -> Chapter -> Questions
    books = list(data.keys())
    for i, b in enumerate(books):
        print(f"{i+1}. {b}")
    
    book_choice = int(input("Select a book: ")) - 1
    selected_book = books[book_choice]
    
    chapters = list(data[selected_book].keys())
    print("\n1. Random Mix (All Chapters)")
    for i, c in enumerate(chapters):
        print(f"{i+2}. {c}")
    
    chap_choice = int(input("Select option: "))
    
    if chap_choice == 1:
        pool = [q for chap in data[selected_book].values() for q in chap]
    else:
        pool = data[selected_book][chapters[chap_choice-2]]

    run_game(pool)

def run_game(questions):
    random.shuffle(questions)
    score = 0
    for q in questions:
        print(f"\n{q['question']}")
        for opt in q['options']:
            print(opt)
        
        user = input("Answer: ").upper()
        if user == q['answer']:
            print("CORRECT!")
            score += 1
        else:
            print(f"WRONG. Correct answer: {q['answer']}")
            
    print(f"\nFinished! Score: {score}/{len(questions)}")

if __name__ == "__main__":
    start_quiz()