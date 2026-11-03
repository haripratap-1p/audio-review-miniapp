import sys
import threading
from http.server import ThreadingHTTPServer

from .config import get_settings
from .http import Handler
from .launcher import pin_launcher
from .reports import post_eod
from .scheduler import scheduler


def main(argv: list[str]) -> None:
    # anything other than eod or pin serves, as before
    if argv[:1] == ["eod"]:
        post_eod(dry="--dry-run" in argv)
    elif argv[:1] == ["pin"]:
        pin_launcher()
    else:
        port = get_settings().port
        print(f"review api on 127.0.0.1:{port}", flush=True)
        threading.Thread(target=scheduler, daemon=True).start()
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
