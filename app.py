import streamlit as st
import json
import random
import os
import zipfile
import io
from PIL import Image

# 1. Load the populated localized cache
CACHE_FILE = 'localized_cache.json'
with open(CACHE_FILE, 'r') as f:
    quiz_data = json.load(f)

def get_image_from_epub(epub_path, image_name):
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            img_path = [name for name in z.namelist() if image_name in name][0]
            with z.open(img_path) as f:
                return Image.open(io.BytesIO(f.read()))
    except: return None

st.title("MCAT Master Quizzer (Fixed)")

# Selection
book = st.sidebar.selectbox("Book", list(quiz_data.keys()))
chapter = st.sidebar.selectbox("Chapter", list(quiz_data[book].keys()))
questions = quiz_data[book][chapter]

if 'idx' not in st.session_state: st.session_state.idx = 0

q = questions[st.session_state.idx]
st.subheader(f"Question {st.session_state.idx + 1} of {len(questions)}")
st.write(q['question'])

# Render Images
if q.get('image_list'):
    cols = st.columns(len(q['image_list']))
    for i, img_name in enumerate(q['image_list']):
        img = get_image_from_epub(q['book_path'], img_name)
        if img: cols[i].image(img)

# FIX: Manually add letters to options for display if they aren't there
letters = ["A", "B", "C", "D"]
display_options = []
for i, opt in enumerate(q['options']):
    prefix = f"{letters[i]}) "
    # Avoid double-prefixing if it already exists
    display_options.append(opt if opt.startswith(prefix) else f"{prefix}{opt}")

user_choice = st.radio("Options:", display_options, key=f"r_{st.session_state.idx}")

if st.button("Submit"):
    st.info("--- UNDER THE HOOD DEBUG ---")
    st.write(f"**Expected (from Key):** `{q['answer']}`")
    st.write(f"**Selected (Raw String):** `{user_choice}`")

    # Convert answer letter to index: A->0, B->1, C->2, D->3
    expected_index = ord(q['answer'].strip().upper()) - ord('A')
    # 
    clean_choice = user_choice.split(")", 1)[-1].strip()

    selected_index = q['options'].index(clean_choice)
    is_correct = selected_index == expected_index

    st.write(f"**Expected Index:** `{expected_index}`")
    st.write(f"**Selected Index:** `{selected_index}`")
    st.write(f"**Comparison Result:** `{is_correct}`")

    if is_correct:
        st.success("Result: MATCH")
    else:
        st.error("Result: MISMATCH")
if st.button("Next Question"):
    st.session_state.idx = (st.session_state.idx + 1) % len(questions)
    st.rerun()