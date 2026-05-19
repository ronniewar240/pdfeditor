# Streamlit PDF Editor

Adobe-style PDF editor starter built with Streamlit.

## Features
- Upload PDF
- Page preview
- Add text overlays
- Draw transparent signature
- Drag/move/resize overlays dynamically
- Delete last overlay / clear page overlays
- Save edited PDF
- Merge PDFs
- Split PDF page ranges
- Rotate pages
- Compress/clean PDF

## Run locally
```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud
1. Create a GitHub repo.
2. Upload `app.py`, `requirements.txt`, and this README.
3. Go to Streamlit Cloud.
4. Create a new app from the repo.
5. Main file path: `app.py`.
6. Deploy.

## Notes
- Use **Transform / Move / Resize** mode to click overlays and drag/resize them.
- Signatures are stored as transparent PNG overlays.
- Export creates a new edited PDF; it does not overwrite the original file.
