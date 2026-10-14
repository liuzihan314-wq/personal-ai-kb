"""Railway launcher using Streamlit's documented custom-route API."""

import os
import threading
from pathlib import Path

import streamlit as st

from pkb.backup import routes


def main():
    # Explicitly enabled one-time maintenance; no public write endpoint.
    if os.getenv("PKB_NOTE_REBUILD_RUN") == "task-047-cloud":
        def maintenance():
            from pkb.notes.rebuild import rebuild
            try:
                rebuild(Path(os.environ["PKB_DATA_DIR"]), "task-047-cloud")
            except Exception as exc:
                print("NOTE_REBUILD stopped=" + type(exc).__name__, flush=True)
        threading.Thread(target=maintenance, daemon=True).start()
    app = st.App(Path(__file__).parent / "ui/app.py", routes=routes())
    app.run(config={
        "server.address": "0.0.0.0", "server.port": int(os.getenv("PORT", "8080")),
        "server.headless": True, "browser.gatherUsageStats": False,
    })


if __name__ == "__main__":
    main()
