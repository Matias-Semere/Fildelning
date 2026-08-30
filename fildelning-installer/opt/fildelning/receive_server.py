#!/usr/bin/env python3

import html
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shares import get_receive
from file_utils import safe_path, format_size


HOST = "127.0.0.1"
PORT = 8001

MAX_FILE_SIZE = 100 * 1024 * 1024 * 1024  # 100 GB


def extract_token(url_path):

    parts = [p for p in url_path.split("/") if p]

    if not parts:
        return None

    if parts[0] == "r":
        parts = parts[1:]

    if not parts:
        return None

    return parts[0]


def page(body):

    return f"""<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>Upload files</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    padding: 30px;
    background: #f3f4f6;
    color: #1f2937;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Arial,
        sans-serif;
}}

.container {{
    max-width: 800px;
    margin: auto;
}}

.card {{
    background: white;
    padding: 30px;
    border-radius: 14px;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
}}

input[type=file] {{
    width: 100%;
    padding: 15px;
    border: 2px dashed #cbd5e1;
    border-radius: 10px;
    margin: 20px 0;
}}

button {{
    padding: 12px 20px;
    border: 0;
    border-radius: 8px;
    background: #2563eb;
    color: white;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
}}

button:disabled {{
    background: #94a3b8;
}}

.progress {{
    margin-top: 20px;
    display: none;
}}

.bar {{
    width: 100%;
    height: 25px;
    background: #e5e7eb;
    border-radius: 20px;
    overflow: hidden;
}}

.fill {{
    width: 0%;
    height: 100%;
    background: #2563eb;
}}

.status {{
    margin-top: 10px;
    font-weight: 600;
}}

.success {{
    color: #15803d;
}}

.error {{
    color: #b91c1c;
}}

</style>

</head>

<body>

<div class="container">

<div class="card">

<h1>📤 Upload files</h1>

<p>
Choose one or more files to upload.
</p>

<input id="files"
       type="file"
       multiple>

<br>

<button id="upload">
Upload
</button>

<div class="progress">

<div class="bar">
<div class="fill" id="fill"></div>
</div>

<div class="status" id="status">
Preparing...
</div>

</div>

</div>

</div>

<script>

const fileInput = document.getElementById("files");
const button = document.getElementById("upload");
const progress = document.querySelector(".progress");
const fill = document.getElementById("fill");
const status = document.getElementById("status");


function formatBytes(bytes) {{

    const units = ["B", "KB", "MB", "GB", "TB"];

    let i = 0;

    while (bytes >= 1024 && i < units.length - 1) {{
        bytes /= 1024;
        i++;
    }}

    return bytes.toFixed(1) + " " + units[i];
}}


function uploadFile(file) {{

    return new Promise((resolve, reject) => {{

        const xhr = new XMLHttpRequest();

        xhr.open(
            "POST",
            window.location.pathname,
            true
        );

        xhr.setRequestHeader(
            "X-File-Name",
            encodeURIComponent(file.name)
        );

        xhr.setRequestHeader(
            "X-File-Size",
            file.size
        );

        xhr.upload.onprogress = function(event) {{

            if (!event.lengthComputable)
                return;

            const percent =
                event.loaded / event.total * 100;

            fill.style.width =
                percent.toFixed(1) + "%";

            status.textContent =
                file.name +
                " — " +
                percent.toFixed(1) +
                "% (" +
                formatBytes(event.loaded) +
                " / " +
                formatBytes(event.total) +
                ")";

        }};


        xhr.onload = function() {{

            if (xhr.status >= 200 &&
                xhr.status < 300) {{

                resolve();

            }} else {{

                reject(
                    new Error(
                        xhr.responseText ||
                        "Upload failed"
                    )
                );

            }}

        }};


        xhr.onerror = function() {{
            reject(
                new Error("Network error")
            );
        }};


        xhr.send(file);

    }});

}}


button.addEventListener("click", async () => {{

    const files = Array.from(fileInput.files);

    if (!files.length) {{
        alert("Choose at least one file.");
        return;
    }}

    button.disabled = true;

    progress.style.display = "block";

    try {{

        for (const file of files) {{

            fill.style.width = "0%";

            await uploadFile(file);

        }}

        fill.style.width = "100%";

        status.textContent =
            "✓ All files uploaded successfully.";

        status.className =
            "status success";

        fileInput.value = "";

    }} catch (error) {{

        status.textContent =
            "✗ " + error.message;

        status.className =
            "status error";

    }} finally {{

        button.disabled = false;

    }}

}});

</script>

</body>

</html>
"""


class ReceiveHandler(BaseHTTPRequestHandler):

    server_version = "PublicReceive/1.0"

    def do_GET(self):

        token = extract_token(urlparse(self.path).path)

        if not token:
            self.send_error(404)
            return

        receive = get_receive(token)

        if not receive:
            self.send_error(404)
            return

        directory = receive["directory"]

        if not os.path.isdir(directory):
            self.send_error(404)
            return

        content = page("").encode("utf-8")

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(content))
        )

        self.end_headers()

        self.wfile.write(content)

    def do_POST(self):

        token = extract_token(urlparse(self.path).path)

        if not token:
            self.send_error(404)
            return

        receive = get_receive(token)

        if not receive:
            self.send_error(404)
            return

        root = receive["directory"]

        if not os.path.isdir(root):
            self.send_error(404)
            return

        filename = self.headers.get("X-File-Name")

        if not filename:
            self.send_error(400, "Missing filename")
            return

        from urllib.parse import unquote

        filename = unquote(filename)

        filename = os.path.basename(filename)

        if not filename or filename in {".", ".."}:
            self.send_error(400, "Invalid filename")
            return

        try:
            size = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return

        if size <= 0:
            self.send_error(400, "Empty file")
            return

        if size > MAX_FILE_SIZE:
            self.send_error(
                413,
                "File is larger than the maximum allowed size"
            )
            return

        try:
            target = safe_path(root, filename)

        except PermissionError:
            self.send_error(403)
            return

        # Don't overwrite an existing file.
        if os.path.exists(target):

            base, ext = os.path.splitext(filename)

            counter = 1

            while True:

                new_name = (
                    f"{base} ({counter}){ext}"
                )

                target = safe_path(
                    root,
                    new_name
                )

                if not os.path.exists(target):
                    filename = new_name
                    break

                counter += 1

        temporary = target + ".uploading"

        try:

            remaining = size

            with open(temporary, "wb") as f:

                while remaining > 0:

                    chunk = self.rfile.read(
                        min(
                            1024 * 1024,
                            remaining
                        )
                    )

                    if not chunk:
                        raise ConnectionError(
                            "Upload ended unexpectedly"
                        )

                    f.write(chunk)

                    remaining -= len(chunk)

                f.flush()
                os.fsync(f.fileno())

            os.replace(
                temporary,
                target
            )

            message = (
                f"Uploaded {filename} "
                f"({format_size(size)})"
            )

            print(message, flush=True)

            response = (
                f"Uploaded {html.escape(filename)}"
            ).encode("utf-8")

            self.send_response(201)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )

            self.send_header(
                "Content-Length",
                str(len(response))
            )

            self.end_headers()

            self.wfile.write(response)

        except Exception as e:

            print(
                f"Upload failed: {e}",
                flush=True
            )

            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass

            self.send_error(
                500,
                "Upload failed"
            )

    def log_message(self, fmt, *args):

        print(
            "%s - - [%s] %s"
            % (
                self.address_string(),
                self.log_date_time_string(),
                fmt % args
            ),
            flush=True
        )


if __name__ == "__main__":

    print(
        f"Receive server listening on "
        f"http://{HOST}:{PORT}",
        flush=True
    )

    server = ThreadingHTTPServer(
        (HOST, PORT),
        ReceiveHandler
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
