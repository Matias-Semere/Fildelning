#!/usr/bin/env python3
import html
import mimetypes
import os
import posixpath
import sys

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shares import get_share
from file_utils import safe_path, format_size, icon_for

HOST = "127.0.0.1"
PORT = 8000


def extract_token_and_path(url_path):
    """
    Accept both:
      /TOKEN
      /TOKEN/path/file
    and, if Tailscale passes the mount point through:
      /s/TOKEN/path/file
    """
    parts = [p for p in url_path.split("/") if p]

    if not parts:
        return None, ""

    if parts[0] == "s":
        parts = parts[1:]

    if not parts:
        return None, ""

    token = parts[0]
    path = "/".join(parts[1:])
    return token, path


def page(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    padding: 30px;
    background: #f3f4f6;
    color: #1f2937;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
}}
.container {{ max-width: 1100px; margin: auto; }}
.header {{
    background: white;
    padding: 25px;
    border-radius: 14px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
}}
.card {{
    background: white;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
}}
table {{ width: 100%; border-collapse: collapse; }}
th {{
    background: #f9fafb;
    text-align: left;
    padding: 15px;
    color: #6b7280;
    font-size: 14px;
}}
td {{ padding: 15px; border-top: 1px solid #eee; }}
.icon {{ width: 50px; font-size: 22px; }}
a {{ color: #2563eb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.download {{
    display: inline-block;
    padding: 9px 14px;
    background: #2563eb;
    color: white;
    border-radius: 7px;
    font-weight: 600;
    white-space: nowrap;
}}
.download:hover {{ background: #1d4ed8; text-decoration: none; }}
.warning {{
    margin-top: 18px;
    padding: 15px;
    background: #fff3cd;
    border: 1px solid #ffca28;
    border-radius: 10px;
    color: #664d03;
    font-weight: 600;
}}
@media (max-width: 700px) {{
    body {{ padding: 10px; }}
    th:nth-child(3), td:nth-child(3) {{ display: none; }}
    td {{ padding: 10px; }}
    .download {{ padding: 8px 10px; font-size: 14px; }}
}}
</style>
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>"""


class ShareHandler(BaseHTTPRequestHandler):
    server_version = "PublicShare/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        token, relative = extract_token_and_path(parsed.path)

        if not token:
            self.send_error(404)
            return

        share = get_share(token)
        if not share:
            self.send_error(404)
            return

        root = share["directory"]
        if not os.path.isdir(root):
            self.send_error(404, "Shared directory no longer exists")
            return

        try:
            target = safe_path(root, relative)
        except PermissionError:
            self.send_error(403)
            return

        if not os.path.exists(target):
            self.send_error(404)
            return

        if os.path.isdir(target):
            self.show_directory(token, root, target, relative)
        else:
            self.send_file(target)

    def show_directory(self, token, root, directory, relative):
        try:
            entries = os.listdir(directory)
        except OSError:
            self.send_error(500)
            return

        entries.sort(key=lambda x: x.lower())
        rows = []

        if relative:
            parent = posixpath.dirname(relative)
            parent_url = "/s/" + token
            if parent:
                parent_url += "/" + "/".join(
                    part.replace("%", "%25") for part in parent.split("/")
                )
            rows.append(f"""
<tr>
<td class="icon">📁</td>
<td colspan="3"><a href="{html.escape(parent_url)}">.. Parent directory</a></td>
</tr>""")

        for name in entries:
            full = os.path.join(directory, name)
            try:
                isdir = os.path.isdir(full)
                size = os.path.getsize(full) if not isdir else 0
            except OSError:
                continue

            safe_name = html.escape(name)
            href_parts = [p for p in relative.split("/") if p]
            href_parts.append(name)
            href = "/s/" + token + "/" + "/".join(
                part.replace("%", "%25").replace(" ", "%20") for part in href_parts
            )

            if isdir:
                display_size = ""
                action = f'<a href="{href}">Open</a>'
            else:
                display_size = format_size(size)
                action = f'<a class="download" href="{href}" download>Download</a>'

            rows.append(f"""
<tr>
<td class="icon">{icon_for(name, isdir)}</td>
<td><a href="{href}">{safe_name}</a></td>
<td>{display_size}</td>
<td>{action}</td>
</tr>""")

        body = f"""
<div class="header">
<h1>Downloads</h1>
<div class="warning">
Please download ONE part at a time.<br>
Wait until the current download is completely finished before starting another one.
</div>
</div>
<div class="card">
<table>
<thead>
<tr><th></th><th>Name</th><th>Size</th><th>Action</th></tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
</div>"""

        content = page("Downloads", body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_file(self, filename):
        try:
            size = os.path.getsize(filename)
        except OSError:
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(filename)[0]
        if not content_type:
            content_type = "application/octet-stream"

        range_header = self.headers.get("Range")
        start, end = 0, size - 1

        if range_header:
            try:
                range_value = range_header.strip().split("=")[1]
                start_str, end_str = range_value.split("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else size - 1
            except (ValueError, IndexError):
                start, end = 0, size - 1

        length = end - start + 1

        try:
            f = open(filename, "rb")
            f.seek(start)
        except OSError:
            self.send_error(404)
            return

        if range_header:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)

        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(filename)}"',
        )
        self.end_headers()

        try:
            remaining = length
            while remaining > 0:
                data = f.read(min(1024 * 1024, remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            f.close()

    def log_message(self, fmt, *args):
        print(
            "%s - - [%s] %s"
            % (self.address_string(), self.log_date_time_string(), fmt % args),
            flush=True,
        )


if __name__ == "__main__":
    print(f"Share server listening on http://{HOST}:{PORT}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), ShareHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()