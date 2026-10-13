"""Text normalisation and boilerplate removal.

Every junk line left in a chunk costs embedding quality and, later, LLM context tokens.
"""

import re
import unicodedata

_BOILERPLATE = re.compile(
    r"^\s*(?:advertisement|sponsored|read more|read also|also read|related:|recommended:|"
    r"subscribe|sign up for|follow us|share this|click here|download our app|"
    r"the post .{0,200} appeared first on .{0,80}|"
    r"this article (?:was )?originally (?:appeared|published)|"
    r"\(?(?:reporting|writing|editing) by .{0,120})\s*\.?\s*$",
    re.IGNORECASE,
)
_FOOTNOTE = re.compile(r"\[\d{1,3}\]")
_SPACES = re.compile(r"[ \t\u00a0]+")


def clean_text(text: str, title: str = "") -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r", "")
    text = _FOOTNOTE.sub("", text)
    out: list[str] = []
    for line in text.split("\n"):
        line = _SPACES.sub(" ", line).strip()
        if not line or _BOILERPLATE.match(line):
            continue
        if out and line == out[-1]:
            continue
        out.append(line)
    if out and title and out[0].casefold() == title.strip().casefold():
        out = out[1:]  # many feeds repeat the headline as the first paragraph
    return "\n".join(out)
