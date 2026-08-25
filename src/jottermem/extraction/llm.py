from __future__ import annotations

import re
from typing import Callable

DEFAULT_PROMPT_TEMPLATE = """\
Extract the atomic, self-contained facts from the text below. Each fact \
should be a single standalone statement that makes sense without the \
others (split compound sentences like "I live in Boston and work at \
Acme" into separate facts). Normalize pronouns to a stated subject \
where possible. Output one fact per line, with no numbering, bullets, \
or commentary. If there are no facts worth remembering, output nothing.

Text:
{text}
"""

_LEADING_MARKER_RE = re.compile(r"^[\s\-*•]*(?:\d+[.)])?\s*")


class LLMExtractor:
    """Extractor that delegates atomic fact extraction to an LLM.

    Provider-agnostic by design: it takes a `complete` callable rather than
    depending on any specific SDK, so using it adds no new dependency and
    works with any LLM API (Anthropic, OpenAI, a local model server, ...).

    Example:
        >>> import anthropic
        >>> client = anthropic.Anthropic()
        >>> def complete(prompt: str) -> str:
        ...     msg = client.messages.create(
        ...         model="claude-sonnet-5",
        ...         max_tokens=512,
        ...         messages=[{"role": "user", "content": prompt}],
        ...     )
        ...     return msg.content[0].text
        >>> extractor = LLMExtractor(complete)
    """

    def __init__(
        self,
        complete: Callable[[str], str],
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    ):
        self.complete = complete
        self.prompt_template = prompt_template

    def extract(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        prompt = self.prompt_template.format(text=text)
        response = self.complete(prompt)
        return self._parse(response)

    def _parse(self, response: str) -> list[str]:
        facts = []
        for line in response.splitlines():
            fact = _LEADING_MARKER_RE.sub("", line).strip()
            if fact:
                facts.append(fact)
        return facts
