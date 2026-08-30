import json
import os
import secrets
import tempfile

SHARES_FILE = "/var/lib/fildelning/shares.json"
RECEIVES_FILE = "/var/lib/fildelning/receives.json"


def _load(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, OSError):
        return {}


def _save(filename, data):
    directory = os.path.dirname(filename)

    fd, temp = tempfile.mkstemp(
        dir=directory,
        prefix=".tmp-",
        text=True
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

        os.replace(temp, filename)

    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_shares():
    return _load(SHARES_FILE)


def load_receives():
    return _load(RECEIVES_FILE)


def create_share(directory):
    shares = load_shares()

    token = secrets.token_urlsafe(24)

    shares[token] = {
        "directory": os.path.abspath(directory)
    }

    _save(SHARES_FILE, shares)

    return token


def create_receive(directory):
    receives = load_receives()

    token = secrets.token_urlsafe(24)

    receives[token] = {
        "directory": os.path.abspath(directory)
    }

    _save(RECEIVES_FILE, receives)

    return token


def get_share(token):
    return load_shares().get(token)


def get_receive(token):
    return load_receives().get(token)


def remove_share(token):
    shares = load_shares()

    if token not in shares:
        return False

    del shares[token]
    _save(SHARES_FILE, shares)

    return True


def remove_receive(token):
    receives = load_receives()

    if token not in receives:
        return False

    del receives[token]
    _save(RECEIVES_FILE, receives)

    return True
