#!/usr/bin/env python3
"""Petit serveur local pour l'Annuaire CCAM Santé.

Usage :
  python server.py                # sert le site sur http://localhost:8000
  python server.py --update       # reconstruit d'abord data/app-data.js depuis les sources en ligne
  python server.py --port 8080    # sert le site sur un port personnalisé
"""
from __future__ import annotations

import argparse
import http.server
import os
import pathlib
import socketserver
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servir le site statique en local")
    parser.add_argument("--update", action="store_true", help="Reconstruire les données avant de lancer le serveur")
    parser.add_argument("--port", type=int, default=8000, help="Port HTTP local")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.update:
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "update_all.py")])

    os.chdir(ROOT)
    with socketserver.TCPServer(("", args.port), Handler) as httpd:
        print(f"Annuaire CCAM Santé lancé : http://localhost:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
