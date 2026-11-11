"""Start a local HouseLens preview without external services or credentials."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent / 'web'


def main():
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    with ThreadingHTTPServer(('127.0.0.1', 8000), handler) as httpd:
        print('HouseLens is running at http://localhost:8000')
        print('Press Ctrl+C to stop the app. Live data needs the scheduled workflow.')
        threading.Timer(1.0, lambda: webbrowser.open('http://localhost:8000')).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
