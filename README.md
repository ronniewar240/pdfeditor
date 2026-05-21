# Flask PDF Editor

Adobe-style PDF editor built with Flask + PDF.js.

## Local run

```bash
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Render deploy

Build command:
```bash
pip install -r requirements.txt
```

Start command:
```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

Required files:
- app.py
- requirements.txt
- runtime.txt
- Procfile
- templates/index.html
