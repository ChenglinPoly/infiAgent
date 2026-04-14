#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exa AI-powered search tool
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from .file_tools import BaseTool, get_abs_path

# Exa SDK import
try:
    from exa_py import Exa
    EXA_AVAILABLE = True
except ImportError:
    EXA_AVAILABLE = False


class ExaSearchTool(BaseTool):
    """Exa AI-powered web search tool"""

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search the web using Exa AI-powered search.

        Parameters:
            query (str): Search query
            max_results (int, optional): Maximum number of results, default 10
            search_type (str, optional): Search type - 'auto' (default), 'neural', 'fast', 'instant'
            content_mode (str, optional): Content retrieval mode - 'highlights' (default), 'text', 'summary', 'none'
            category (str, optional): Filter by category - 'company', 'research paper', 'news', 'personal site', 'financial report', 'people'
            include_domains (list, optional): Only include results from these domains
            exclude_domains (list, optional): Exclude results from these domains
            include_text (list, optional): Strings that must appear in page text
            exclude_text (list, optional): Strings to exclude from results
            start_published_date (str, optional): ISO 8601 date; only results published after this
            end_published_date (str, optional): ISO 8601 date; only results published before this
            save_path (str, optional): Relative path to save results as a .md file
        """
        try:
            if not EXA_AVAILABLE:
                return {
                    "status": "error",
                    "output": "",
                    "error": "exa-py not installed. Run: pip install exa-py"
                }

            api_key = os.environ.get("EXA_API_KEY", "")
            if not api_key:
                return {
                    "status": "error",
                    "output": "",
                    "error": "EXA_API_KEY environment variable is not set. Get your key from: https://exa.ai"
                }

            query = parameters.get("query")
            if not query:
                return {
                    "status": "error",
                    "output": "",
                    "error": "query is required"
                }

            max_results = parameters.get("max_results", 10)
            search_type = parameters.get("search_type", "auto")
            content_mode = parameters.get("content_mode", "highlights")
            category = parameters.get("category")
            include_domains = parameters.get("include_domains")
            exclude_domains = parameters.get("exclude_domains")
            include_text = parameters.get("include_text")
            exclude_text = parameters.get("exclude_text")
            start_published_date = parameters.get("start_published_date")
            end_published_date = parameters.get("end_published_date")
            save_path = parameters.get("save_path")

            # Create Exa client with integration tracking header
            client = Exa(api_key=api_key)
            client.headers["x-exa-integration"] = "infiagent"

            # Build search kwargs
            search_kwargs: Dict[str, Any] = {
                "query": query,
                "num_results": max_results,
                "type": search_type,
            }

            # Add content retrieval parameters
            if content_mode == "highlights":
                search_kwargs["highlights"] = {"max_characters": 4000}
            elif content_mode == "text":
                search_kwargs["text"] = {"max_characters": 10000}
            elif content_mode == "summary":
                search_kwargs["summary"] = True

            # Add optional filters
            if category:
                search_kwargs["category"] = category
            if include_domains:
                search_kwargs["include_domains"] = include_domains
            if exclude_domains:
                search_kwargs["exclude_domains"] = exclude_domains
            if include_text:
                search_kwargs["include_text"] = include_text
            if exclude_text:
                search_kwargs["exclude_text"] = exclude_text
            if start_published_date:
                search_kwargs["start_published_date"] = start_published_date
            if end_published_date:
                search_kwargs["end_published_date"] = end_published_date

            # Execute search
            if content_mode and content_mode != "none":
                response = client.search_and_contents(**search_kwargs)
            else:
                response = client.search(**search_kwargs)

            # Format results as Markdown
            results_md = []
            results_md.append(f"# Exa Search Results: {query}\n")
            results_md.append(f"Total: {len(response.results)} results\n")

            for i, result in enumerate(response.results, 1):
                title = getattr(result, "title", "No title") or "No title"
                url = getattr(result, "url", "") or ""
                published_date = getattr(result, "publishedDate", None) or getattr(result, "published_date", None)
                author = getattr(result, "author", None)

                results_md.append(f"## {i}. {title}\n")
                results_md.append(f"**URL**: {url}\n")
                if published_date:
                    results_md.append(f"**Published**: {published_date}\n")
                if author:
                    results_md.append(f"**Author**: {author}\n")

                # Extract content with fallback cascade
                snippet = _extract_snippet(result)
                if snippet:
                    results_md.append(f"**Snippet**: {snippet}\n")

            results_text = '\n'.join(results_md)

            # Save to file
            if save_path:
                save_path_obj = Path(save_path)
                safe_query = re.sub(r'[^\w\s-]', '', query).strip()
                safe_query = re.sub(r'[-\s]+', '_', safe_query)[:50]

                new_filename = f"{save_path_obj.stem}_{safe_query}_n{max_results}{save_path_obj.suffix}"
                final_save_path = str(save_path_obj.parent / new_filename)

                abs_save_path = get_abs_path(task_id, final_save_path)
                abs_save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(abs_save_path, 'w', encoding='utf-8') as f:
                    f.write(results_text)

                output = f"Results saved to {final_save_path}"
            else:
                output = results_text

            return {
                "status": "success",
                "output": output,
                "error": ""
            }

        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


def _extract_snippet(result: Any) -> str:
    """
    Extract the best available content snippet from an Exa result,
    cascading through highlights -> summary -> text.
    """
    # Try highlights first
    highlights = getattr(result, "highlights", None)
    if highlights and isinstance(highlights, list) and len(highlights) > 0:
        return "\n".join(highlights)

    # Try summary
    summary = getattr(result, "summary", None)
    if summary and isinstance(summary, str) and summary.strip():
        return summary.strip()

    # Try text (truncate to keep output manageable)
    text = getattr(result, "text", None)
    if text and isinstance(text, str) and text.strip():
        truncated = text.strip()[:2000]
        if len(text.strip()) > 2000:
            truncated += "..."
        return truncated

    return ""
