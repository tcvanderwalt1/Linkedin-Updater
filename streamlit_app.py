"""Root entrypoint for Streamlit Community Cloud.

Prefer deploying with Main file path: streamlit_app.py
(or keep app/streamlit_app.py — both work after the path fix).
"""

from app.streamlit_app import main

if __name__ == "__main__":
    main()
else:
    # Streamlit executes the script as a module without __main__
    main()
