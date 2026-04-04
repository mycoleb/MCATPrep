import streamlit as st
import json
import random
from PIL import Image
import zipfile
import io

# Load your question database
with open('quiz_cache.json', 'r') as f:
    quiz_data = json.load(f)

def get_image_from_epub(epub_path, image_name):
    """Extracts a specific image from the EPUB zip container"""
    with zipfile.ZipFile(epub_path, 'r') as z:
        # Search for the image path within the zip
        img_path = [name for name in z.namelist() if image_name in name][0]
        with z.open(img_path) as f:
            return Image.open(io.BytesIO(f.read()))

st.title("MCAT Organic Chemistry Quiz")

# State management to keep the same question across clicks
if 'current_q' not in st.session_state:
    st.session_state.current_q = random.choice(quiz_data["Chapter 1"])

q = st.session_state.current_q

st.subheader(f"Question: {q['question']}")

# --- IMAGE LOGIC ---
# If your JSON question data includes an 'image_file' key
if 'image_file' in q:
    book_path = "MCAT Organic Chemistry Review 2026-2027.epub"
    img = get_image_from_epub(book_path, q['image_file'])
    st.image(img, caption="Analyze the structure above to answer", width=400)

# Choice selection
choice = st.radio("Select your answer:", q['options'])

if st.button("Submit Answer"):
    if choice.startswith(q['answer']):
        st.success("Correct!")
    else:
        st.error(f"Incorrect. The correct answer was {q['answer']}.")