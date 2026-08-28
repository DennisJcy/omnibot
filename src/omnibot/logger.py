import sys
from datetime import datetime


def log(*args, **kwargs):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}]", *args, file=sys.stderr, flush=True, **kwargs)
