"""CLI interface for the coding agent."""

import sys
import os
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

from .agent import Agent

custom_theme = Theme({
    "tool": "cyan",
    "tool_output": "dim",
    "error": "red bold",
    "info": "dim cyan",
    "prompt": "green bold",
})

console = Console(theme=custom_theme)

BANNER = """[dim cyan]┌──────────────────────────────────┐
│  quoka-agent v0.1.0              │
│  CLI coding agent powered by     │
│  Claude                          │
│                                  │
│  Commands:                       │
│    /quit     exit                 │
│    /reset    clear history        │
│    /tokens   show token usage     │
│    /model    show current model   │
│    /help     show this help       │
└──────────────────────────────────┘[/dim cyan]"""


def render_events(events: list[dict]):
    """Render agent events to the terminal."""
    for event in events:
        match event["type"]:
            case "text":
                console.print()
                console.print(Markdown(event["content"]))

            case "tool_use":
                name = event["name"]
                inp = event["input"]

                # Compact display for each tool
                match name:
                    case "read_file":
                        detail = inp.get("path", "")
                    case "write_file":
                        detail = inp.get("path", "")
                        size = len(inp.get("content", ""))
                        detail = f"{detail} ({size} bytes)"
                    case "edit_file":
                        detail = inp.get("path", "")
                    case "run_command":
                        detail = inp.get("command", "")
                    case "list_directory":
                        detail = inp.get("path", ".")
                    case "search_files":
                        detail = f"/{inp.get('pattern', '')}/ in {inp.get('path', '.')}"
                    case _:
                        detail = str(inp)

                console.print(f"  [tool]⚡ {name}[/tool] [dim]{detail}[/dim]")

            case "tool_result":
                output = event["output"]
                # Truncate long output for display
                lines = output.split("\n")
                if len(lines) > 20:
                    display = "\n".join(lines[:15]) + f"\n  ... ({len(lines)} lines total)"
                else:
                    display = output
                console.print(f"  [tool_output]{display}[/tool_output]")


def handle_command(cmd: str, agent: Agent) -> bool:
    """Handle slash commands. Returns True if the REPL should continue."""
    cmd = cmd.strip().lower()

    match cmd:
        case "/quit" | "/exit" | "/q":
            console.print("[info]Bye.[/info]")
            return False
        case "/reset":
            agent.reset()
            console.print("[info]Conversation reset.[/info]")
        case "/tokens":
            usage = agent.token_usage
            console.print(f"[info]Tokens: {usage['input']:,} in / {usage['output']:,} out / {usage['total']:,} total[/info]")
        case "/model":
            console.print(f"[info]Model: {agent.model}[/info]")
        case "/help":
            console.print(BANNER)
        case _:
            console.print(f"[error]Unknown command: {cmd}[/error]")

    return True


def main():
    """Entry point for the CLI agent."""
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[error]ANTHROPIC_API_KEY not set. Export it and try again.[/error]")
        sys.exit(1)

    # Allow model override via env var
    model = os.environ.get("QUOKA_MODEL", "claude-sonnet-4-20250514")

    console.print(BANNER)
    console.print(f"[info]Working directory: {os.getcwd()}[/info]")
    console.print(f"[info]Model: {model}[/info]")
    console.print()

    agent = Agent(model=model)

    while True:
        try:
            user_input = console.input("[prompt]> [/prompt]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[info]Bye.[/info]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if not handle_command(user_input, agent):
                break
            continue

        try:
            events = agent.send(user_input)
            render_events(events)
            console.print()
        except Exception as e:
            console.print(f"[error]Error: {e}[/error]")
            console.print()


if __name__ == "__main__":
    main()
