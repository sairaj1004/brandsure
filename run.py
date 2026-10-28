"""Start BrandSure:  python run.py   then open http://localhost:8000"""
import os

from backend.app import create_app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", "8000"))
    print(f"BrandSure is running at http://localhost:{port}")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=False, threaded=True)
