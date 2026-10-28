"""Entry point for production servers (Render uses: gunicorn wsgi:app)."""
from backend.app import create_app

app = create_app()
