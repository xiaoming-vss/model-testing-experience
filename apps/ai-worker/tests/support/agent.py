"""Agent stand-ins for runner tests; no collected cases."""

from collections.abc import Callable


class FakeResult:
    """One reply of a fake agent."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeBot:
    """Agent stand-in that is also an async context manager.

    ``replies`` is either a list consumed in order, so a call past its end fails, or a
    function of the message. ``calls`` records the message and session key of each run;
    the session key is keyword-only, as every caller in the worker passes it.
    """

    def __init__(self, replies: list[str] | Callable[[str], str]) -> None:
        self.replies = replies
        self.calls: list[dict[str, str]] = []

    async def __aenter__(self) -> "FakeBot":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def run(self, message: str, *, session_key: str) -> FakeResult:
        self.calls.append({"message": message, "session_key": session_key})
        replies = self.replies
        content = replies(message) if callable(replies) else replies[len(self.calls) - 1]
        return FakeResult(content)


class FakeFactory:
    """``from_config`` stand-in: records its keyword arguments and always hands out its bot."""

    def __init__(self, replies: list[str] | Callable[[str], str]) -> None:
        self.last_kwargs: dict[str, str | None] | None = None
        self.bot = FakeBot(replies)

    def __call__(self, **kwargs):
        self.last_kwargs = kwargs
        return self.bot
