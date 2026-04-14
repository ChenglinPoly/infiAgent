"""
Tests for the Exa AI-powered search tool.

These tests mock the exa-py SDK and verify:
- API response parsing and content fallback logic
- Content mode routing (highlights/text/summary/none)
- Integration header is set
- Disabled state (SDK missing, API key missing)
- File saving behavior
- Optional filter pass-through
"""

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Module-level setup: load exa_tools without triggering the heavy __init__.py
# ---------------------------------------------------------------------------

def _load_exa_tools():
    """
    Import exa_tools.py directly, bypassing tool_server_lite/tools/__init__.py
    which pulls in litellm, PIL, etc.  We stub only the lightweight file_tools
    dependency that exa_tools actually needs.
    """
    # Ensure the package hierarchy exists in sys.modules
    if "tool_server_lite" not in sys.modules:
        pkg = types.ModuleType("tool_server_lite")
        pkg.__path__ = [str(Path(__file__).resolve().parent.parent / "tool_server_lite")]
        sys.modules["tool_server_lite"] = pkg

    if "tool_server_lite.tools" not in sys.modules:
        tools_pkg = types.ModuleType("tool_server_lite.tools")
        tools_pkg.__path__ = [str(Path(__file__).resolve().parent.parent / "tool_server_lite" / "tools")]
        sys.modules["tool_server_lite.tools"] = tools_pkg

    # Load file_tools (the only real dependency of exa_tools)
    ft_path = Path(__file__).resolve().parent.parent / "tool_server_lite" / "tools" / "file_tools.py"
    ft_spec = importlib.util.spec_from_file_location("tool_server_lite.tools.file_tools", str(ft_path))
    ft_mod = importlib.util.module_from_spec(ft_spec)
    sys.modules["tool_server_lite.tools.file_tools"] = ft_mod
    ft_spec.loader.exec_module(ft_mod)

    # Load exa_tools
    exa_path = Path(__file__).resolve().parent.parent / "tool_server_lite" / "tools" / "exa_tools.py"
    exa_spec = importlib.util.spec_from_file_location("tool_server_lite.tools.exa_tools", str(exa_path))
    exa_mod = importlib.util.module_from_spec(exa_spec)
    sys.modules["tool_server_lite.tools.exa_tools"] = exa_mod
    exa_spec.loader.exec_module(exa_mod)
    return exa_mod


_exa_mod = _load_exa_tools()
ExaSearchTool = _exa_mod.ExaSearchTool
_extract_snippet = _exa_mod._extract_snippet


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path)


def _make_result(
    title="Example Title",
    url="https://example.com",
    highlights=None,
    summary=None,
    text=None,
    published_date=None,
    author=None,
):
    result = MagicMock()
    result.title = title
    result.url = url
    result.highlights = highlights
    result.summary = summary
    result.text = text
    result.publishedDate = published_date
    result.published_date = published_date
    result.author = author
    return result


def _make_response(results):
    resp = MagicMock()
    resp.results = results
    return resp


EXA_RESPONSE_FIXTURE = _make_response([
    _make_result(
        title="Intro to LLMs",
        url="https://example.com/llms",
        highlights=["Large language models are transformers trained on vast text corpora."],
        published_date="2025-01-15",
        author="Jane Doe",
    ),
    _make_result(
        title="RAG Explained",
        url="https://example.com/rag",
        highlights=None,
        summary="Retrieval-augmented generation combines search with LLMs.",
    ),
    _make_result(
        title="Vector Databases",
        url="https://example.com/vectordb",
        highlights=None,
        summary=None,
        text="Vector databases store embeddings for similarity search. " * 20,
    ),
])


# ---------------------------------------------------------------------------
# Import guard / disabled state
# ---------------------------------------------------------------------------

class TestExaToolDisabled:
    def test_returns_error_when_sdk_missing(self, workspace):
        with patch.object(_exa_mod, "EXA_AVAILABLE", False), \
             patch.dict(os.environ, {}, clear=True):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {"query": "test"})
            assert result["status"] == "error"
            assert "exa-py" in result["error"]

    def test_returns_error_when_api_key_missing(self, workspace):
        with patch.object(_exa_mod, "EXA_AVAILABLE", True), \
             patch.dict(os.environ, {}, clear=True):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {"query": "test"})
            assert result["status"] == "error"
            assert "EXA_API_KEY" in result["error"]


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

class TestExaToolValidation:
    def test_returns_error_when_query_missing(self, workspace):
        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {})
            assert result["status"] == "error"
            assert "query" in result["error"]


# ---------------------------------------------------------------------------
# Response parsing & content fallback
# ---------------------------------------------------------------------------

class TestExaToolResponseParsing:
    def test_parse_highlights_response(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = EXA_RESPONSE_FIXTURE

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {"query": "LLMs", "content_mode": "highlights"})

        assert result["status"] == "success"
        assert "Intro to LLMs" in result["output"]
        assert "https://example.com/llms" in result["output"]
        assert "Jane Doe" in result["output"]
        assert "2025-01-15" in result["output"]
        assert "transformers" in result["output"]

    def test_parse_summary_fallback(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = EXA_RESPONSE_FIXTURE

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {"query": "RAG"})

        assert result["status"] == "success"
        assert "RAG Explained" in result["output"]
        assert "Retrieval-augmented generation" in result["output"]

    def test_parse_text_fallback(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = EXA_RESPONSE_FIXTURE

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {"query": "vector databases"})

        assert result["status"] == "success"
        assert "Vector Databases" in result["output"]
        assert "embeddings" in result["output"]

    def test_empty_content_fields(self, workspace):
        empty_response = _make_response([
            _make_result(title="Empty Result", url="https://example.com/empty"),
        ])
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = empty_response

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {"query": "nothing"})

        assert result["status"] == "success"
        assert "Empty Result" in result["output"]


# ---------------------------------------------------------------------------
# Snippet extraction unit tests
# ---------------------------------------------------------------------------

class TestExtractSnippet:
    def test_prefers_highlights(self):
        r = _make_result(highlights=["h1", "h2"], summary="s", text="t")
        assert "h1" in _extract_snippet(r)
        assert "h2" in _extract_snippet(r)

    def test_falls_back_to_summary(self):
        r = _make_result(highlights=None, summary="my summary", text="t")
        assert _extract_snippet(r) == "my summary"

    def test_falls_back_to_text(self):
        r = _make_result(highlights=None, summary=None, text="some text")
        assert _extract_snippet(r) == "some text"

    def test_truncates_long_text(self):
        long_text = "a" * 5000
        r = _make_result(highlights=None, summary=None, text=long_text)
        snippet = _extract_snippet(r)
        assert len(snippet) <= 2004  # 2000 + "..."
        assert snippet.endswith("...")

    def test_returns_empty_for_no_content(self):
        r = _make_result(highlights=None, summary=None, text=None)
        assert _extract_snippet(r) == ""


# ---------------------------------------------------------------------------
# Content mode routing
# ---------------------------------------------------------------------------

class TestExaToolContentModes:
    def test_none_mode_calls_search(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search.return_value = _make_response([])

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            tool.execute(workspace, {"query": "test", "content_mode": "none"})

        mock_client.search.assert_called_once()
        mock_client.search_and_contents.assert_not_called()

    def test_text_mode_passes_text_param(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = _make_response([])

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            tool.execute(workspace, {"query": "test", "content_mode": "text"})

        call_kwargs = mock_client.search_and_contents.call_args[1]
        assert "text" in call_kwargs
        assert call_kwargs["text"] == {"max_characters": 10000}

    def test_summary_mode_passes_summary_param(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = _make_response([])

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            tool.execute(workspace, {"query": "test", "content_mode": "summary"})

        call_kwargs = mock_client.search_and_contents.call_args[1]
        assert "summary" in call_kwargs
        assert call_kwargs["summary"] is True

    def test_highlights_mode_passes_highlights_param(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = _make_response([])

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            tool.execute(workspace, {"query": "test", "content_mode": "highlights"})

        call_kwargs = mock_client.search_and_contents.call_args[1]
        assert "highlights" in call_kwargs
        assert call_kwargs["highlights"] == {"max_characters": 4000}


# ---------------------------------------------------------------------------
# Integration header
# ---------------------------------------------------------------------------

class TestExaToolIntegrationHeader:
    def test_sets_integration_header(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = _make_response([])

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            tool.execute(workspace, {"query": "test"})

        assert mock_client.headers["x-exa-integration"] == "infiagent"


# ---------------------------------------------------------------------------
# Save to file
# ---------------------------------------------------------------------------

class TestExaToolSaveToFile:
    def test_saves_results_to_file(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = EXA_RESPONSE_FIXTURE

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            result = tool.execute(workspace, {
                "query": "LLMs",
                "save_path": "temp/exa_search/results.md",
            })

        assert result["status"] == "success"
        assert "Results saved to" in result["output"]

        saved_files = list(Path(workspace).rglob("*.md"))
        assert len(saved_files) == 1
        content = saved_files[0].read_text(encoding="utf-8")
        assert "Intro to LLMs" in content


# ---------------------------------------------------------------------------
# Optional filters
# ---------------------------------------------------------------------------

class TestExaToolFilters:
    def test_passes_optional_filters(self, workspace):
        mock_client = MagicMock()
        mock_client.headers = {}
        mock_client.search_and_contents.return_value = _make_response([])

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), \
             patch.object(_exa_mod, "Exa", return_value=mock_client):
            tool = ExaSearchTool()
            tool.execute(workspace, {
                "query": "AI news",
                "category": "news",
                "include_domains": ["techcrunch.com", "theverge.com"],
                "exclude_domains": ["reddit.com"],
                "include_text": ["artificial intelligence"],
                "exclude_text": ["crypto"],
                "start_published_date": "2025-01-01T00:00:00Z",
                "end_published_date": "2025-12-31T23:59:59Z",
                "search_type": "neural",
            })

        call_kwargs = mock_client.search_and_contents.call_args[1]
        assert call_kwargs["category"] == "news"
        assert call_kwargs["include_domains"] == ["techcrunch.com", "theverge.com"]
        assert call_kwargs["exclude_domains"] == ["reddit.com"]
        assert call_kwargs["include_text"] == ["artificial intelligence"]
        assert call_kwargs["exclude_text"] == ["crypto"]
        assert call_kwargs["start_published_date"] == "2025-01-01T00:00:00Z"
        assert call_kwargs["end_published_date"] == "2025-12-31T23:59:59Z"
        assert call_kwargs["type"] == "neural"
