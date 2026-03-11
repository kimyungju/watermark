# WatermarkOff

Remove watermarks from PDFs and images — no signup, no hassle.

## What It Does

Upload watermarked PDFs or images and get clean versions back. Supports platform watermarks (StuDocu, Scribd, CourseHero) and generic watermarks.

- **PDF**: Object-level removal preserving text selectability and formatting — no rasterization
- **Images**: OpenCV-based detection and inpainting

## Quick Start

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows/Git Bash
pip install -r requirements.txt
uvicorn main:app --reload       # http://localhost:8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

The frontend proxies `/api` requests to the backend automatically.

## Tech Stack

| Layer    | Stack                                      |
|----------|---------------------------------------------|
| Backend  | Python 3.13, FastAPI, PyMuPDF, pypdf, OpenCV |
| Frontend | React 19, Vite 7, Tailwind CSS v4            |
| Deploy   | Render (backend) + Vercel (frontend)         |

## Limits

- File types: `.png`, `.jpg`, `.jpeg`, `.pdf`
- Max file size: 10 MB
- Max files per upload: 5
- Max PDF pages: 20

## License

MIT
