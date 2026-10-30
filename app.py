# Entry point for Render / Hugging Face Spaces / `python app.py`
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from shabbos_prep.app import build

port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or 7860)
build().launch(server_name="0.0.0.0", server_port=port)
