import tempfile, shutil
from contextlib import contextmanager

@contextmanager
def temp_workdir(prefix: str = "avatar_"):
    d = tempfile.mkdtemp(prefix=prefix)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
