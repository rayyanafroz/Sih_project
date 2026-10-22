"""Reset the database and storage to the known demo state.

Usage (from backend/):
    .venv/bin/python -m scripts.reset_demo               # keep existing demo documents
    .venv/bin/python -m scripts.reset_demo --regenerate  # also rebuild the synthetic PDFs/images
"""
import sys

from app.demo.seed import reset

if __name__ == "__main__":
    reset(generate_documents="--regenerate" in sys.argv)
    print("Demo reset complete. Sign in with scrutiny@verifyai.demo / demo1234")
