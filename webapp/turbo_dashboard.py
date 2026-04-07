from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


st.set_page_config(page_title="Turbo Buff", layout="wide")

navigation = st.navigation(
    [
        st.Page(
            "webapp/dashboard_page.py",
            title="Dashboard",
            url_path="",
            default=True,
        ),
        st.Page(
            "pages/Database.py",
            title="Database",
            url_path="database",
        ),
    ],
    position="sidebar",
)
navigation.run()
