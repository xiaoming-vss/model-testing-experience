"""In-memory object storage stand-in shared by document tests; no collected cases."""

import threading


class Body:
    """One stored object as the storage client hands it back."""

    def __init__(self, data, *, chunked=False):
        self.data = data
        self.chunked = chunked
        self.closed = False

    def iter_chunks(self, chunk_size):
        if not self.chunked:
            yield self.data
            return
        yield self.data[:chunk_size]
        if len(self.data) > chunk_size:
            yield self.data[chunk_size:]

    def close(self):
        self.closed = True


class Storage:
    """Serve fixed objects and record how the code under test reads them.

    Pass ``data`` for one object stored under ``key``, or ``objects`` for several. ``calls``
    counts reads and ``opened`` lists each returned ``(key, body)``. With ``fail`` set a read
    raises, which proves a path never touched storage; with ``block`` set a read signals
    ``entered`` and then waits for ``release``.
    """

    def __init__(self, data=None, *, key="document", objects=None, chunked=False):
        self.objects = {} if objects is None else objects
        self.key = None if objects is not None else key
        if data is not None:
            self.objects[self.key] = data
        self.chunked = chunked
        self.calls = 0
        self.opened = []
        self.fail = False
        self.block = False
        self.entered = threading.Event()
        self.release = threading.Event()

    @property
    def data(self):
        """Content of the single object; reassign it to simulate a replaced file."""
        return self.objects[self.key]

    @data.setter
    def data(self, value):
        self.objects[self.key] = value

    def get_object(self, key):
        self.calls += 1
        if self.fail:
            raise RuntimeError("object should not be read on replay")
        if self.key is not None:
            assert key == self.key
        if self.block:
            self.entered.set()
            if not self.release.wait(10):
                raise RuntimeError("test storage timed out")
        body = Body(self.objects[key], chunked=self.chunked)
        self.opened.append((key, body))
        return {"Body": body}
