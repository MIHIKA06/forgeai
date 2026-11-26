"""Central configuration. Everything is overridable with environment variables so the
same code runs against a local Ollama, Groq, or any OpenAI-compatible endpoint."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Settings:
    # OpenAI-compatible endpoint. Default: local Ollama.
    base_url: str = field(default_factory=lambda: _env("FORGE_BASE_URL", "http://localhost:11434/v1"))
    api_key: str = field(default_factory=lambda: _env("FORGE_API_KEY", "ollama"))
    # Model that runs the factory stages AND the generated agent.
    model: str = field(default_factory=lambda: _env("FORGE_MODEL", "qwen2.5:7b"))
    # Judge deliberately defaults to a *different model family* to blunt self-preference bias.
    judge_model: str = field(default_factory=lambda: _env("FORGE_JUDGE_MODEL", "llama3.1:8b"))
    # Embeddings are optional; retrieval falls back to BM25 if unavailable.
    embed_model: str = field(default_factory=lambda: _env("FORGE_EMBED_MODEL", "nomic-embed-text"))
    embed_base_url: str = field(default_factory=lambda: _env("FORGE_EMBED_BASE_URL", _env("FORGE_BASE_URL", "http://localhost:11434/v1")))
    cache_dir: Path = field(default_factory=lambda: Path(_env("FORGE_CACHE_DIR", str(ROOT / ".cache"))))
    use_cache: bool = field(default_factory=lambda: _env("FORGE_CACHE", "1") == "1")
    request_timeout: float = field(default_factory=lambda: float(_env("FORGE_TIMEOUT", "180")))
    seed: int = 7
    # When FORGE_MODEL is set explicitly (e.g. on a hosted deployment that uses Groq instead of Ollama),
    # it overrides the model name stored inside saved agent definitions.
    model_overridden: bool = field(default_factory=lambda: bool(os.environ.get("FORGE_MODEL")))


SETTINGS = Settings()
