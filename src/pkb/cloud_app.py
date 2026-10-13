"""Railway launcher using Streamlit's documented custom-route API."""

import os
from pathlib import Path

import streamlit as st

from pkb.backup import routes


def main():
    app = st.App(Path(__file__).parent / "ui/app.py", routes=routes())
    app.run(config={
        "server.address": "0.0.0.0", "server.port": int(os.getenv("PORT", "8080")),
        "server.headless": True, "browser.gatherUsageStats": False,
    })


if __name__ == "__main__":
    main()
