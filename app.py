# Entry point for Hugging Face Spaces / `python app.py`
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from shabbos_prep.app import build
build().launch(server_name="0.0.0.0")
