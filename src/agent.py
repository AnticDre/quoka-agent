"""Core agent loop: sends messages to Claude, handles tool calls, iterates."""

import anthropic
from .tools import TOOL_SCHEMAS, execute_tool

DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_ITERATIONS = 25  # safety limit per user message


SYSTEM_PROMPT = """You are a coding agent running in a CLI environment. You help the user by reading, writing, and editing files, running commands, and solving programming tasks.

Your working directory is the user's current directory. You have access to these tools:
- read_file: read file contents
- write_file: create or overwrite files
- edit_file: find-and-replace within a file (old_str must be unique)
- run_command: execute shell commands (tests, git, installs, etc.)
- list_directory: list files in a directory
- search_files: grep for patterns across files

Guidelines:
- Read existing files before editing them
- Run tests after making changes when tests exist
- Keep explanations brief. Show your work through tool use, not narration
- If something fails, read the error, diagnose, and fix it
- Ask the user for clarification if the task is ambiguous
"""


class Agent:
    """The agentic loop: user message -> Claude -> tool calls -> repeat."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic()
        self.model = model
        self.messages: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def send(self, user_message: str) -> list[dict]:
        """Send a user message and run the agentic loop until done.

        Returns a list of events for the UI to render:
        [
            {"type": "text", "content": "..."},
            {"type": "tool_use", "name": "...", "input": {...}},
            {"type": "tool_result", "name": "...", "output": "..."},
        ]
        """
        self.messages.append({"role": "user", "content": user_message})
        events = []

        for _ in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
            )

            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens

            # Process response content blocks
            assistant_content = response.content
            self.messages.append({"role": "assistant", "content": assistant_content})

            # Collect text blocks and tool use blocks
            tool_uses = []
            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    events.append({"type": "text", "content": block.text})
                elif block.type == "tool_use":
                    events.append({
                        "type": "tool_use",
                        "name": block.name,
                        "input": block.input,
                    })
                    tool_uses.append(block)

            # If no tool calls, we're done
            if response.stop_reason == "end_turn" or not tool_uses:
                break

            # Execute tools and build tool results
            tool_results = []
            for tool_use in tool_uses:
                output = execute_tool(tool_use.name, tool_use.input)
                events.append({
                    "type": "tool_result",
                    "name": tool_use.name,
                    "output": output,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": output,
                })

            # Add tool results as user message and continue loop
            self.messages.append({"role": "user", "content": tool_results})

        return events

    @property
    def token_usage(self) -> dict:
        return {
            "input": self.total_input_tokens,
            "output": self.total_output_tokens,
            "total": self.total_input_tokens + self.total_output_tokens,
        }

    def reset(self):
        """Clear conversation history."""
        self.messages = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
