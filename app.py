import io
import json
import os
import zipfile

import streamlit as st
from PIL import Image

CACHE_FILE = "localized_cache.json"


def load_cache():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def get_cache():
    return load_cache()


def get_image_from_epub(epub_path: str, image_name: str):
    if not epub_path or not image_name:
        return None

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            matches = []
            for name in zf.namelist():
                if name.endswith(image_name) or os.path.basename(name) == image_name:
                    matches.append(name)

            if not matches:
                return None

            with zf.open(matches[0]) as f:
                img_bytes = f.read()
                return Image.open(io.BytesIO(img_bytes))
    except Exception:
        return None


def render_image_list(epub_path: str, image_list, width=400):
    if not image_list:
        return

    for image_name in image_list:
        img = get_image_from_epub(epub_path, image_name)
        if img is not None:
            st.image(img, width=width)
        else:
            st.warning(f"Could not load image: {image_name}")


def init_state():
    defaults = {
        "idx": 0,
        "score": 0,
        "answered": {},
        "last_book": None,
        "last_section": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_section_state():
    st.session_state.idx = 0
    st.session_state.score = 0
    st.session_state.answered = {}


def get_choice_key(book: str, section: str, idx: int) -> str:
    return f"choice::{book}::{section}::{idx}"


def answer_letter_to_index(letter: str) -> int:
    letter = (letter or "").strip().upper()
    if letter in ["A", "B", "C", "D"]:
        return ord(letter) - ord("A")
    return -1


def display_option(option_index: int, option: dict):
    letter = chr(ord("A") + option_index)
    text = option.get("text", "").strip()
    return f"{letter}) {text}" if text else f"{letter}) [Image Option]"


def sort_sections(section_names):
    return sorted(section_names, key=lambda s: s.lower())


st.set_page_config(page_title="MCAT Master Quizzer", layout="wide")
st.title("MCAT Master Quizzer")

init_state()
quiz_data = get_cache()

if not quiz_data:
    st.error("localized_cache.json is empty or missing data.")
    st.stop()

book_names = sorted(quiz_data.keys(), key=lambda s: s.lower())
book = st.sidebar.selectbox("Book", book_names)

section_names = sort_sections(list(quiz_data[book].keys()))
section = st.sidebar.selectbox("Section", section_names)

if st.session_state.last_book != book or st.session_state.last_section != section:
    reset_section_state()
    st.session_state.last_book = book
    st.session_state.last_section = section

if st.sidebar.button("Reset Section Progress"):
    reset_section_state()
    st.rerun()

questions = quiz_data[book][section]

if not questions:
    st.error("No questions found in this section.")
    st.stop()

if st.session_state.idx >= len(questions):
    st.session_state.idx = 0

q = questions[st.session_state.idx]
choice_key = get_choice_key(book, section, st.session_state.idx)

st.write(f"**Book:** {book}")
st.write(f"**Section:** {section}")
st.write(f"**Score:** {st.session_state.score} / {len(st.session_state.answered)}")
st.subheader(f"Question {st.session_state.idx + 1} of {len(questions)}")

if q.get("source_file"):
    st.caption(f"Source XHTML: {q['source_file']}")

question_text = q.get("question", "").strip()
if question_text:
    st.text(question_text)
else:
    st.write("_No stem text extracted for this question._")

if q.get("image_list"):
    st.markdown("**Question images**")
    render_image_list(q["book_path"], q["image_list"], width=450)

options = q.get("options", [])
if not options:
    st.error("This question has no answer choices.")
    st.stop()

display_options = [display_option(i, opt) for i, opt in enumerate(options)]

selected_label = st.radio("Options:", display_options, key=choice_key)

for i, opt in enumerate(options):
    if opt.get("images"):
        with st.expander(f"Show image(s) for option {chr(ord('A') + i)}"):
            render_image_list(q["book_path"], opt["images"], width=300)

qid = f"{book}|{section}|{st.session_state.idx}"

if st.button("Submit"):
    selected_index = display_options.index(selected_label)
    expected_index = answer_letter_to_index(q.get("answer", ""))
    is_correct = selected_index == expected_index

    if qid not in st.session_state.answered:
        st.session_state.answered[qid] = {
            "selected_index": selected_index,
            "expected_index": expected_index,
            "is_correct": is_correct,
        }
        if is_correct:
            st.session_state.score += 1

    st.info("--- UNDER THE HOOD DEBUG ---")
    st.write(f"**Expected (from Key):** `{q.get('answer', '')}`")
    st.write(f"**Selected (Raw String):** `{selected_label}`")
    st.write(f"**Selected Index:** `{selected_index}`")
    st.write(f"**Expected Index:** `{expected_index}`")
    st.write(f"**Comparison Result:** `{is_correct}`")

    if is_correct:
        st.success("Result: MATCH")
    else:
        st.error("Result: MISMATCH")
        if 0 <= expected_index < len(display_options):
            st.write(f"**Correct Answer:** {display_options[expected_index]}")

if qid in st.session_state.answered:
    saved = st.session_state.answered[qid]
    if saved["is_correct"]:
        st.success("Already answered correctly.")
    else:
        st.error("Already answered incorrectly.")
        if 0 <= saved["expected_index"] < len(display_options):
            st.write(f"Correct answer: {display_options[saved['expected_index']]}")

col1, col2 = st.columns(2)

with col1:
    if st.button("Previous Question"):
        st.session_state.idx = (st.session_state.idx - 1) % len(questions)
        st.rerun()

with col2:
    if st.button("Next Question"):
        st.session_state.idx = (st.session_state.idx + 1) % len(questions)
        st.rerun()