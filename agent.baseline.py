"""Two-tool tutorial baseline. No persistent memory."""
import os
from datetime import datetime

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama


@tool
def current_time() -> str:
    """Get the current local date and time."""
    return datetime.now().isoformat(sep=" ", timespec="seconds")


@tool
def word_count(text: str) -> int:
    """Count whitespace-separated words."""
    return len(text.split())


def build_agent():
    return create_agent(
        model=ChatOllama(
            model=os.getenv("CHAT_MODEL", "qwen3.5:4b"),
            temperature=0,
        ),
        tools=[current_time, word_count],
        system_prompt="You are a helpful assistant with access to tools.",
    )
