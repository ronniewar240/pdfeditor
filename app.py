import base64
import io
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF
import streamlit as st
from PIL import Image
from pypdf import PdfReader, PdfWriter
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="PDF Studio - Streamlit", page_icon="📄", layout="wide")

CUSTOM_CSS = """
<style>
.stApp { background: #0f1117; color: #f3f4f6; }
[data-testid="stSidebar"] { background: #141824; }
.block-container { padding-top: 1.2rem; }
.tool-card {
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.04);
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 12px;
}
.small-muted { color: #9ca3af; font-size: 0.9rem; }
.adobe-title { font-size: 1.7rem; font-weight: 800; letter-spacing: -0.02em; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def init_state():
    defaults = {
        "pdf_bytes": None,
        "pdf_name": "uploaded.pdf",
        "page_overlays": {},
        "signature_png": None,
        "canvas_seed": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def open_pdf(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def render_page(pdf_bytes: bytes, page_index: int, zoom: float = 1.5) -> Tuple[Image.Image, fitz.Rect]:
    doc = open_pdf(pdf_bytes)
    page = doc[page_index]
    rect = page.rect
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    doc.close()
    return img, rect


def image_to_base64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def normalize_canvas_objects(json_data) -> List[Dict]:
    if not json_data or "objects" not in json_data:
        return []
    objects = []
    for obj in json_data["objects"]:
        if obj.get("type") in {"text", "i-text", "textbox", "image"}:
            objects.append(obj)
    return objects


def make_text_object(text: str, left=120, top=120, font_size=24) -> Dict:
    return {
        "type": "textbox",
        "version": "4.4.0",
        "originX": "left",
        "originY": "top",
        "left": left,
        "top": top,
        "width": max(160, len(text) * font_size * 0.6),
        "height": font_size * 1.5,
        "fill": "#111111",
        "stroke": None,
        "strokeWidth": 1,
        "fontFamily": "Arial",
        "fontSize": font_size,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "lineHeight": 1.16,
        "text": text,
        "textAlign": "left",
        "scaleX": 1,
        "scaleY": 1,
        "angle": 0,
    }


def make_signature_object(signature_png: bytes, left=140, top=180, width=220) -> Dict:
    img = Image.open(io.BytesIO(signature_png)).convert("RGBA")
    w, h = img.size
    data_url = "data:image/png;base64," + base64.b64encode(signature_png).decode("utf-8")
    return {
        "type": "image",
        "version": "4.4.0",
        "originX": "left",
        "originY": "top",
        "left": left,
        "top": top,
        "width": w,
        "height": h,
        "scaleX": width / w,
        "scaleY": width / w,
        "angle": 0,
        "src": data_url,
        "crossOrigin": None,
    }


def transparent_signature_from_canvas(canvas_result) -> bytes | None:
    if canvas_result.image_data is None:
        return None
    img = Image.fromarray(canvas_result.image_data.astype("uint8"), "RGBA")
    bbox = img.getbbox()
    if not bbox:
        return None
    img = img.crop(bbox)
    datas = img.getdata()
    new_data = []
    for r, g, b, a in datas:
        # remove white/near-white background, keep dark ink
        if r > 245 and g > 245 and b > 245:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def decode_data_url(data_url: str) -> bytes:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url)


def apply_overlays(pdf_bytes: bytes, overlays_by_page: Dict[int, List[Dict]], zoom: float) -> bytes:
    doc = open_pdf(pdf_bytes)
    for page_index, objects in overlays_by_page.items():
        if not objects or page_index >= len(doc):
            continue
        page = doc[page_index]
        for obj in objects:
            left = float(obj.get("left", 0)) / zoom
            top = float(obj.get("top", 0)) / zoom
            width = float(obj.get("width", 0)) * float(obj.get("scaleX", 1)) / zoom
            height = float(obj.get("height", 0)) * float(obj.get("scaleY", 1)) / zoom
            angle = float(obj.get("angle", 0))
            rect = fitz.Rect(left, top, left + width, top + height)

            if obj.get("type") in {"textbox", "text", "i-text"}:
                text = obj.get("text", "")
                font_size = float(obj.get("fontSize", 20)) * float(obj.get("scaleY", 1)) / zoom
                color = obj.get("fill", "#111111") or "#111111"
                rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)) if color.startswith("#") else (0, 0, 0)
                page.insert_textbox(rect, text, fontsize=max(font_size, 6), fontname="helv", color=rgb, rotate=0)

            elif obj.get("type") == "image" and obj.get("src"):
                img_bytes = decode_data_url(obj["src"])
                page.insert_image(rect, stream=img_bytes, rotate=int(angle) if angle in {0, 90, 180, 270} else 0, overlay=True)
    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    return out.getvalue()


def merge_pdfs(files) -> bytes:
    writer = PdfWriter()
    for f in files:
        reader = PdfReader(f)
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def split_pdf(pdf_file, ranges: str) -> bytes:
    reader = PdfReader(pdf_file)
    writer = PdfWriter()
    total = len(reader.pages)
    for part in ranges.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = [int(x.strip()) for x in part.split("-", 1)]
        else:
            start = end = int(part)
        start = max(1, start)
        end = min(total, end)
        for p in range(start - 1, end):
            writer.add_page(reader.pages[p])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def rotate_pdf(pdf_file, degrees: int) -> bytes:
    reader = PdfReader(pdf_file)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def compress_pdf(pdf_bytes: bytes) -> bytes:
    doc = open_pdf(pdf_bytes)
    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    return out.getvalue()


init_state()

with st.sidebar:
    st.markdown('<div class="adobe-title">PDF Studio</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">Streamlit deploy version</div>', unsafe_allow_html=True)
    st.divider()

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if uploaded:
        st.session_state.pdf_bytes = uploaded.read()
        st.session_state.pdf_name = uploaded.name
        st.session_state.page_overlays = {}
        st.session_state.canvas_seed += 1

    tool = st.radio(
        "Tools",
        ["Edit PDF", "Merge PDFs", "Split PDF", "Rotate PDF", "Compress PDF"],
        label_visibility="collapsed",
    )

st.title("📄 Adobe-style PDF Editor")
st.caption("Upload, add text, sign, move, resize, delete, and export edited PDFs.")

if tool == "Merge PDFs":
    st.subheader("Merge PDFs")
    merge_files = st.file_uploader("Choose PDFs to merge", type=["pdf"], accept_multiple_files=True)
    if st.button("Merge PDFs", disabled=not merge_files):
        merged = merge_pdfs(merge_files)
        st.download_button("Download merged PDF", merged, "merged.pdf", "application/pdf")

elif tool == "Split PDF":
    st.subheader("Split PDF")
    split_file = st.file_uploader("Choose PDF to split", type=["pdf"], key="split")
    ranges = st.text_input("Pages to keep", value="1-2", help="Examples: 1-3, 5, 8-10")
    if st.button("Create split PDF", disabled=not split_file):
        result = split_pdf(split_file, ranges)
        st.download_button("Download split PDF", result, "split.pdf", "application/pdf")

elif tool == "Rotate PDF":
    st.subheader("Rotate PDF")
    rotate_file = st.file_uploader("Choose PDF to rotate", type=["pdf"], key="rotate")
    degrees = st.selectbox("Rotation", [90, 180, 270])
    if st.button("Rotate PDF", disabled=not rotate_file):
        result = rotate_pdf(rotate_file, degrees)
        st.download_button("Download rotated PDF", result, "rotated.pdf", "application/pdf")

elif tool == "Compress PDF":
    st.subheader("Compress PDF")
    comp_file = st.file_uploader("Choose PDF to compress", type=["pdf"], key="compress")
    if st.button("Compress PDF", disabled=not comp_file):
        data = comp_file.read()
        result = compress_pdf(data)
        st.success(f"Reduced/cleaned from {len(data)/1024:.1f} KB to {len(result)/1024:.1f} KB")
        st.download_button("Download compressed PDF", result, "compressed.pdf", "application/pdf")

else:
    if not st.session_state.pdf_bytes:
        st.info("Upload a PDF from the left sidebar to start editing.")
        st.stop()

    doc = open_pdf(st.session_state.pdf_bytes)
    page_count = len(doc)
    doc.close()

    left, right = st.columns([0.72, 0.28], gap="large")
    with right:
        st.markdown('<div class="tool-card">', unsafe_allow_html=True)
        page_number = st.number_input("Page", min_value=1, max_value=page_count, value=1, step=1)
        zoom = st.slider("Preview zoom", 1.0, 2.5, 1.5, 0.1)
        page_index = int(page_number) - 1
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="tool-card">', unsafe_allow_html=True)
        st.subheader("Add text")
        text_value = st.text_input("Text", value="Your text")
        font_size = st.slider("Font size", 10, 72, 24)
        if st.button("Add text box"):
            objs = st.session_state.page_overlays.get(page_index, [])
            objs.append(make_text_object(text_value, font_size=font_size))
            st.session_state.page_overlays[page_index] = objs
            st.session_state.canvas_seed += 1
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="tool-card">', unsafe_allow_html=True)
        st.subheader("Signature")
        sig_canvas = st_canvas(
            fill_color="rgba(255,255,255,0)",
            stroke_width=3,
            stroke_color="#111111",
            background_color="#ffffff",
            height=160,
            width=320,
            drawing_mode="freedraw",
            key="signature_canvas",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save signature"):
                sig = transparent_signature_from_canvas(sig_canvas)
                if sig:
                    st.session_state.signature_png = sig
                    st.success("Signature saved")
        with c2:
            if st.button("Add signature", disabled=not st.session_state.signature_png):
                objs = st.session_state.page_overlays.get(page_index, [])
                objs.append(make_signature_object(st.session_state.signature_png))
                st.session_state.page_overlays[page_index] = objs
                st.session_state.canvas_seed += 1
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="tool-card">', unsafe_allow_html=True)
        st.subheader("Delete")
        d1, d2 = st.columns(2)
        with d1:
            if st.button("Delete last item"):
                objs = st.session_state.page_overlays.get(page_index, [])
                if objs:
                    objs.pop()
                    st.session_state.page_overlays[page_index] = objs
                    st.session_state.canvas_seed += 1
                    st.rerun()
        with d2:
            if st.button("Clear page"):
                st.session_state.page_overlays[page_index] = []
                st.session_state.canvas_seed += 1
                st.rerun()
        st.caption("To move or resize: select an overlay on the page, then drag it or its corner handles.")
        st.markdown("</div>", unsafe_allow_html=True)

    with left:
        page_img, page_rect = render_page(st.session_state.pdf_bytes, page_index, zoom=zoom)
        initial_json = {"version": "4.4.0", "objects": st.session_state.page_overlays.get(page_index, [])}
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=1,
            background_image=page_img,
            update_streamlit=True,
            height=page_img.height,
            width=page_img.width,
            drawing_mode="transform",
            initial_drawing=initial_json,
            key=f"main_canvas_{page_index}_{st.session_state.canvas_seed}",
        )

        current_objects = normalize_canvas_objects(canvas_result.json_data)
        st.session_state.page_overlays[page_index] = current_objects

        if st.button("Save edited PDF", type="primary"):
            edited = apply_overlays(st.session_state.pdf_bytes, st.session_state.page_overlays, zoom=zoom)
            st.download_button("Download edited PDF", edited, "edited_pdf.pdf", "application/pdf")
