import base64
import io
import os
import re
import uuid
from pathlib import Path

import fitz  # PyMuPDF
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
OUTPUT_DIR = BASE_DIR / "static" / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_pdf_path(file_id: str) -> Path:
    if not re.match(r"^[a-f0-9\-]{36}\.pdf$", file_id):
        raise ValueError("Invalid file id")
    path = UPLOAD_DIR / file_id
    if not path.exists():
        raise FileNotFoundError("PDF not found")
    return path


def parse_data_url(data_url: str) -> bytes:
    if not data_url or "," not in data_url:
        raise ValueError("Invalid image data")
    header, encoded = data_url.split(",", 1)
    if "base64" not in header:
        raise ValueError("Image data must be base64")
    return base64.b64decode(encoded)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_pdf():
    file = request.files.get("pdf")
    if not file or file.filename == "":
        return jsonify({"error": "No PDF uploaded"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    original = secure_filename(file.filename)
    file_id = f"{uuid.uuid4()}.pdf"
    saved_path = UPLOAD_DIR / file_id
    file.save(saved_path)

    try:
        with fitz.open(saved_path) as doc:
            pages = [{"width": p.rect.width, "height": p.rect.height} for p in doc]
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        return jsonify({"error": f"Could not read PDF: {exc}"}), 400

    return jsonify({
        "file_id": file_id,
        "name": original,
        "url": f"/pdf/{file_id}",
        "pages": pages,
    })


@app.route("/pdf/<file_id>")
def serve_pdf(file_id):
    return send_from_directory(UPLOAD_DIR, file_id, mimetype="application/pdf")


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.route("/apply", methods=["POST"])
def apply_edits():
    data = request.get_json(silent=True) or {}
    file_id = data.get("file_id")
    annotations = data.get("annotations", [])

    if not file_id:
        return jsonify({"error": "Missing file id"}), 400

    try:
        input_path = safe_pdf_path(file_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    output_name = f"edited-{uuid.uuid4()}.pdf"
    output_path = OUTPUT_DIR / output_name

    try:
        doc = fitz.open(input_path)
        for item in annotations:
            page_index = int(item.get("page", 1)) - 1
            if page_index < 0 or page_index >= len(doc):
                continue
            page = doc[page_index]
            x = float(item.get("x", 0))
            y = float(item.get("y", 0))
            w = max(1.0, float(item.get("w", 100)))
            h = max(1.0, float(item.get("h", 40)))
            kind = item.get("type")

            if kind == "text":
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                font_size = max(6, min(96, float(item.get("fontSize", 18))))
                rect = fitz.Rect(x, y, x + w, y + h)
                page.insert_textbox(
                    rect,
                    text,
                    fontsize=font_size,
                    fontname="helv",
                    color=(0, 0, 0),
                    align=fitz.TEXT_ALIGN_LEFT,
                )

            elif kind == "signature":
                data_url = item.get("image")
                if not data_url:
                    continue
                image_bytes = parse_data_url(data_url)
                rect = fitz.Rect(x, y, x + w, y + h)
                page.insert_image(rect, stream=image_bytes, keep_proportion=True, overlay=True)

        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
    except Exception as exc:
        return jsonify({"error": f"Could not save PDF: {exc}"}), 500

    return jsonify({"download_url": f"/download/{output_name}", "filename": output_name})


@app.route("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
