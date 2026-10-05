"""Questions and answers kept for this running process."""

from __future__ import annotations

_turns: list[dict[str, str]] = []
_FOLLOW = {
    "that",
    "those",
    "them",
    "it",
    "its",
    "same",
    "above",
    "previous",
    "earlier",
    "again",
    "more",
    "also",
    "there",
}


def remember(question: str, answer: str) -> None:
    text = " ".join((answer or "").split())
    if len(text) < 8:
        return
    _turns.append({"question": question.strip(), "answer": text[:700]})
    del _turns[:-8]


def prompt_block() -> str:
    if not _turns:
        return ""
    lines = ["Session so far:"]
    for turn in _turns[-6:]:
        lines.append(f"Asked: {turn['question']}\nAnswer: {turn['answer']}")
    return "\n\n".join(lines)


def follow_up(question: str) -> str:
    if not _turns:
        return question
    words = [word.strip(".,?!") for word in question.lower().split()]
    if len(words) <= 14 or any(word in _FOLLOW for word in words):
        return f"{_turns[-1]['question']}. Follow-up: {question}"
    return question
