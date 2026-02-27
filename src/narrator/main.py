"""CLI entrypoint for project bootstrap."""

from narrator.config import load_config


def main() -> None:
    app_config = load_config()
    print(f"narrator scaffold ready with provider: {app_config.llm.default_provider}")
