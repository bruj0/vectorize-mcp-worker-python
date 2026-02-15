"""Shared test fixtures.

Provides mock protocol implementations so business logic can be tested
without the Cloudflare runtime or JS FFI.

Also ensures the `workers` stub is importable when running outside the
Cloudflare runtime (i.e., local pytest runs).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add stubs directory to sys.path so `import workers` resolves to our stub
# when running outside the Cloudflare runtime.
_stubs_dir = str(Path(__file__).parent / "stubs")
if _stubs_dir not in sys.path:
    sys.path.insert(0, _stubs_dir)


@pytest.fixture
def sample_text() -> str:
    """A multi-paragraph text for chunking tests."""
    return (
        "Artificial intelligence is transforming the way we work.\n\n"
        "Machine learning models can now understand and generate human language "
        "with remarkable accuracy. This has led to breakthroughs in translation, "
        "summarization, and question answering.\n\n"
        "Deep learning architectures like transformers have become the foundation "
        "of modern NLP. Models like BERT, GPT, and their successors have set new "
        "benchmarks across virtually every language understanding task.\n\n"
        "The practical applications are vast: from chatbots and virtual assistants "
        "to content moderation and sentiment analysis. Organizations of all sizes "
        "are finding ways to leverage these technologies.\n\n"
        "However, challenges remain. Bias in training data, hallucination in "
        "generated outputs, and the environmental cost of training large models "
        "are active areas of research and concern."
    )


@pytest.fixture
def short_text() -> str:
    """Short text that fits in a single chunk."""
    return "This is a short document for testing purposes."
