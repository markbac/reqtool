"""The re-entrant lock decorator shared by Store and its mixins."""

from __future__ import annotations

import functools


def _locked(fn):
    """Run a Store method while holding the store's re-entrant lock.

    Mutators are read-modify-write sequences over shared dicts and YAML files;
    without this, concurrent requests lose each other's updates.
    """
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            self._revision += 1  # a call that may write invalidates derived caches before it reads any ...
            try:
                return fn(self, *args, **kwargs)
            finally:
                self._revision += 1  # ... and again after it has written
    return wrapper
