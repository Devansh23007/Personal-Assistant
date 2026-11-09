import os
import sys
import time
import threading
import urllib.request
import webview
import uvicorn

# Ensure the backend directory is in the Python path
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def start_server():
    """Runs the FastAPI backend in a background thread."""
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


def wait_for_server(url="http://127.0.0.1:8000/api/health", timeout=10):
    """Waits until the backend server is ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    # 1. Start server in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 2. Wait for backend to be online
    wait_for_server()

    # 3. Create native desktop window
    window = webview.create_window(
        title="J.A.R.V.I.S. - MARK VII",
        url="http://127.0.0.1:8000/",
        width=1240,
        height=820,
        min_size=(900, 600),
        background_color="#030712",
        text_select=False,
    )

    # 4. Start the native desktop GUI event loop
    webview.start()


if __name__ == "__main__":
    main()
