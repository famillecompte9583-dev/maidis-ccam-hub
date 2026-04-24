#!/usr/bin/env python3
"""Petit serveur local pour postes internes.
Usage :
  python server.py             # sert le site sur http://localhost:8000
  python server.py --update    # reconstruit d'abord data/app-data.js depuis les sources en ligne
"""
import http.server, socketserver, subprocess, sys, pathlib, os
ROOT = pathlib.Path(__file__).resolve().parent
if '--update' in sys.argv:
    subprocess.check_call([sys.executable, str(ROOT/'scripts'/'update_all.py')])
os.chdir(ROOT)
PORT = 8000
class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'application/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8'}
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Maidis CCAM Hub lancé : http://localhost:{PORT}")
    httpd.serve_forever()
