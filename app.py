import os
import uuid
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify, url_for
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
from pypdf import PdfWriter, PdfReader
import base64


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 120 * 1024 * 1024
ALLOWED = {"pdf"}


def is_pdf(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def save_upload(file):
    if not file or not is_pdf(file.filename):
        raise ValueError("Please upload a PDF file.")
    safe_name = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = UPLOAD_DIR / unique_name
    file.save(path)
    return path


def output_path(prefix="edited"):
    return OUTPUT_DIR / f"{prefix}_{uuid.uuid4().hex}.pdf"


def parse_pages(text: str, total: int):
    text = (text or "all").strip().lower()
    if text in ["", "all", "*"]:
        return list(range(total))
    pages = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            start, end = int(start), int(end)
            if start > end:
                start, end = end, start
            pages.extend(range(start - 1, end))
        else:
            pages.append(int(part) - 1)
    pages = [p for p in dict.fromkeys(pages) if 0 <= p < total]
    if not pages:
        raise ValueError("No valid pages selected.")
    return pages


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def info():
    try:
        pdf = save_upload(request.files.get("pdf"))
        doc = fitz.open(pdf)
        data = {
            "pages": doc.page_count,
            "metadata": doc.metadata,
            "filename": pdf.name,
            "original_name": request.files.get("pdf").filename,
        }
        doc.close()
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/merge", methods=["POST"])
def merge():
    try:
        files = request.files.getlist("pdfs")
        if len(files) < 2:
            raise ValueError("Upload at least 2 PDFs to merge.")
        writer = PdfWriter()
        for f in files:
            path = save_upload(f)
            reader = PdfReader(str(path))
            for page in reader.pages:
                writer.add_page(page)
        out = output_path("merged")
        with open(out, "wb") as fp:
            writer.write(fp)
        return send_file(out, as_attachment=True, download_name="merged.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/split", methods=["POST"])
def split():
    try:
        pdf = save_upload(request.files.get("pdf"))
        pages_raw = request.form.get("pages", "").strip()
        doc = fitz.open(pdf)
        selected = parse_pages(pages_raw, doc.page_count)
        new_doc = fitz.open()
        for p in selected:
            new_doc.insert_pdf(doc, from_page=p, to_page=p)
        out = output_path("split")
        new_doc.save(out)
        new_doc.close(); doc.close()
        return send_file(out, as_attachment=True, download_name="selected_pages.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/delete-pages", methods=["POST"])
def delete_pages():
    try:
        pdf = save_upload(request.files.get("pdf"))
        pages_raw = request.form.get("pages", "").strip()
        doc = fitz.open(pdf)
        selected = set(parse_pages(pages_raw, doc.page_count))
        keep = [i for i in range(doc.page_count) if i not in selected]
        if not keep:
            raise ValueError("You cannot delete every page.")
        new_doc = fitz.open()
        for p in keep:
            new_doc.insert_pdf(doc, from_page=p, to_page=p)
        out = output_path("deleted_pages")
        new_doc.save(out)
        new_doc.close(); doc.close()
        return send_file(out, as_attachment=True, download_name="pages_deleted.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/reorder", methods=["POST"])
def reorder():
    try:
        pdf = save_upload(request.files.get("pdf"))
        order_raw = request.form.get("order", "").strip()
        if not order_raw:
            raise ValueError("Enter page order like 3,1,2,4-6.")
        doc = fitz.open(pdf)
        order = parse_pages(order_raw, doc.page_count)
        new_doc = fitz.open()
        for p in order:
            new_doc.insert_pdf(doc, from_page=p, to_page=p)
        out = output_path("reordered")
        new_doc.save(out)
        new_doc.close(); doc.close()
        return send_file(out, as_attachment=True, download_name="reordered.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/rotate", methods=["POST"])
def rotate():
    try:
        pdf = save_upload(request.files.get("pdf"))
        degrees = int(request.form.get("degrees", "90"))
        if degrees not in [90, 180, 270]:
            raise ValueError("Rotation must be 90, 180, or 270 degrees.")
        doc = fitz.open(pdf)
        pages = parse_pages(request.form.get("pages", "all"), doc.page_count)
        for idx in pages:
            page = doc[idx]
            page.set_rotation((page.rotation + degrees) % 360)
        out = output_path("rotated")
        doc.save(out)
        doc.close()
        return send_file(out, as_attachment=True, download_name="rotated.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/watermark", methods=["POST"])
def watermark():
    try:
        pdf = save_upload(request.files.get("pdf"))
        text = request.form.get("text", "CONFIDENTIAL").strip() or "CONFIDENTIAL"
        size = int(request.form.get("size", "54"))
        opacity = float(request.form.get("opacity", "0.16"))
        doc = fitz.open(pdf)
        for page in doc:
            rect = page.rect
            page.insert_textbox(rect, text, fontsize=size, color=(0.55, 0.55, 0.55), rotate=45, align=1, overlay=True, fill_opacity=opacity)
        out = output_path("watermarked")
        doc.save(out, garbage=4, deflate=True)
        doc.close()
        return send_file(out, as_attachment=True, download_name="watermarked.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/add-text", methods=["POST"])
def add_text():
    try:
        pdf = save_upload(request.files.get("pdf"))
        text = request.form.get("text", "").strip()
        page_num = int(request.form.get("page", "1")) - 1
        x = float(request.form.get("x", "72"))
        y = float(request.form.get("y", "72"))
        size = int(request.form.get("size", "14"))
        if not text:
            raise ValueError("Text cannot be empty.")
        doc = fitz.open(pdf)
        if not 0 <= page_num < doc.page_count:
            raise ValueError("Invalid page number.")
        doc[page_num].insert_text((x, y), text, fontsize=size, color=(0, 0, 0))
        out = output_path("text_added")
        doc.save(out, garbage=4, deflate=True)
        doc.close()
        return send_file(out, as_attachment=True, download_name="text_added.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/sign", methods=["POST"])
def sign_pdf():
    try:
        pdf = save_upload(request.files.get("pdf"))
        signature_data = request.form.get("signature", "").strip()
        page_num = int(request.form.get("page", "1")) - 1
        x = float(request.form.get("x", "72"))
        y = float(request.form.get("y", "120"))
        width = float(request.form.get("width", "180"))
        if not signature_data.startswith("data:image/png;base64,"):
            raise ValueError("Draw or upload a signature first.")
        img_bytes = base64.b64decode(signature_data.split(",", 1)[1])
        doc = fitz.open(pdf)
        if not 0 <= page_num < doc.page_count:
            raise ValueError("Invalid page number.")
        page = doc[page_num]
        height = width * 0.38
        rect = fitz.Rect(x, y, x + width, y + height)
        page.insert_image(rect, stream=img_bytes, overlay=True, keep_proportion=True)
        out = output_path("signed")
        doc.save(out, garbage=4, deflate=True)
        doc.close()
        return send_file(out, as_attachment=True, download_name="signed.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


def hex_to_rgb(hex_color: str):
    hex_color = (hex_color or "#000000").strip().lstrip("#")
    if len(hex_color) != 6:
        return (0, 0, 0)
    return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))


@app.route("/api/apply-edits", methods=["POST"])
def apply_edits():
    try:
        import json
        pdf = save_upload(request.files.get("pdf"))
        annotations = json.loads(request.form.get("annotations", "[]"))
        doc = fitz.open(pdf)
        for item in annotations:
            page_num = int(item.get("page", 1)) - 1
            if not 0 <= page_num < doc.page_count:
                continue
            page = doc[page_num]
            x = float(item.get("x", 72))
            y = float(item.get("y", 72))
            w = float(item.get("w", 180))
            h = float(item.get("h", 40))
            if item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                size = max(6, float(item.get("size", 14)))
                color = hex_to_rgb(item.get("color", "#000000"))
                rect = fitz.Rect(x, y, x + w, y + h)
                page.insert_textbox(rect, text, fontsize=size, color=color, align=0, overlay=True)
            elif item.get("type") == "signature":
                data = str(item.get("data", ""))
                if not data.startswith("data:image/png;base64,"):
                    continue
                img_bytes = base64.b64decode(data.split(",", 1)[1])
                rect = fitz.Rect(x, y, x + w, y + h)
                page.insert_image(rect, stream=img_bytes, overlay=True, keep_proportion=True)
        out = output_path("dynamic_edited")
        doc.save(out, garbage=4, deflate=True)
        doc.close()
        return send_file(out, as_attachment=True, download_name="edited_dynamic.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/compress", methods=["POST"])
def compress():
    try:
        pdf = save_upload(request.files.get("pdf"))
        doc = fitz.open(pdf)
        out = output_path("compressed")
        doc.save(out, garbage=4, deflate=True, clean=True)
        doc.close()
        return send_file(out, as_attachment=True, download_name="compressed.pdf")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
