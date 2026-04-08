from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


navigation = st.navigation(
    [
        st.Page(
            Path(__file__).with_name("dashboard_page.py"),
            title="Dashboard",
            url_path="",
            default=True,
        ),
        st.Page(
            PROJECT_ROOT / "pages" / "Database.py",
            title="Database",
            url_path="database",
        ),
    ],
    position="sidebar",
)
navigation.run()
