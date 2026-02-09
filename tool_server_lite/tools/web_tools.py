#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络工具 - 使用 crawl4ai
"""

from pathlib import Path
from typing import Dict, Any
import asyncio
import re
import requests
from urllib.parse import urlencode
from .file_tools import BaseTool, get_abs_path

# Crawl4AI 导入
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
except (ImportError, TypeError, Exception):
    CRAWL4AI_AVAILABLE = False

# DuckDuckGo 导入
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """
    crawl4ai 的返回对象在不同版本/运行环境下可能是:
    - 一个带属性的对象 (result.markdown / result.cleaned_html ...)
    - 或者被序列化/包装成 dict
    这里统一做兼容读取，避免 `getattr(...)=None` 造成误判。
    """
    try:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
    except Exception:
        return default


class CrawlPageTool(BaseTool):
    """网页爬取工具 - 使用 crawl4ai"""
    
    async def execute_async(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        爬取网页内容
        
        Parameters:
            url (str): 网页URL
            save_path (str, optional): 保存结果的相对路径（.md文件）
            download_images (bool, optional): 是否下载图片，默认False
        """
        try:
            if not CRAWL4AI_AVAILABLE:
                return {
                    "status": "error",
                    "output": "",
                    "error": "crawl4ai not installed. Run: pip install crawl4ai"
                }
            
            url = parameters.get("url")
            save_path = parameters.get("save_path")
            download_images = parameters.get("download_images", False)
            
            if not url:
                return {
                    "status": "error",
                    "output": "",
                    "error": "url is required"
                }
            
            # 爬取页面
            markdown_text = await self._crawl_page(url)
            
            # 处理图片
            if not download_images:
                # 移除图片标记
                markdown_text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", markdown_text)
            
            # 保存到文件
            if save_path:
                abs_save_path = get_abs_path(task_id, save_path)
                abs_save_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(abs_save_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_text)
                
                output = f"结果保存在 {save_path}"
            else:
                output = markdown_text
            
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
    
    async def _crawl_page(self, url: str) -> str:
        """使用 crawl4ai 爬取页面"""
        browser_conf = BrowserConfig(headless=True, verbose=False)
        run_conf = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            result = await crawler.arun(url, config=run_conf)
            
            # 先看 crawl4ai 是否明确失败
            success = _get_field(result, "success", None)
            if success is False:
                err = _get_field(result, "error_message", "") or _get_field(result, "error", "") or ""
                raise Exception(f"crawl4ai failed: {err[:300]}")

            markdown_attr = _get_field(result, "markdown", None)
            if markdown_attr is None:
                # 输出可诊断信息，便于定位不同版本的字段差异
                if isinstance(result, dict):
                    keys = list(result.keys())[:60]
                    raise Exception(f"Unable to extract markdown from crawl result (missing field: markdown; dict keys sample={keys})")
                attrs = [a for a in dir(result) if not a.startswith("_")][:60]
                raise Exception(f"Unable to extract markdown from crawl result (missing field: markdown; attrs sample={attrs})")

            try:
                markdown_text = (
                    _get_field(markdown_attr, "raw_markdown", None)
                    or _get_field(markdown_attr, "markdown", None)
                    or str(markdown_attr)
                )
            except Exception:
                markdown_text = str(markdown_attr)

            if not (isinstance(markdown_text, str) and markdown_text.strip()):
                # 不做兜底：确保“原生使用 crawl4ai 的 markdown”才算成功
                mtype = type(markdown_attr).__name__
                raw_len = 0
                md_len = 0
                try:
                    raw_len = len((_get_field(markdown_attr, "raw_markdown", "") or ""))
                except Exception:
                    raw_len = 0
                try:
                    md_len = len((_get_field(markdown_attr, "markdown", "") or ""))
                except Exception:
                    md_len = 0
                raise Exception(f"Unable to extract markdown from crawl result (markdown empty; type={mtype}; raw_markdown_len={raw_len}; markdown_len={md_len})")

            return markdown_text


class GoogleScholarSearchTool(BaseTool):
    """谷歌学术搜索工具 - 使用 crawl4ai"""
    
    async def execute_async(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        谷歌学术搜索
        
        Parameters:
            query (str): 搜索关键词
            year_low (int, optional): 年份下限
            year_high (int, optional): 年份上限
            pages (int, optional): 爬取页数，默认1
            save_path (str, optional): 保存结果的相对路径（.md文件）
        """
        try:
            if not CRAWL4AI_AVAILABLE:
                return {
                    "status": "error",
                    "output": "",
                    "error": "crawl4ai not installed. Run: pip install crawl4ai"
                }
            
            query = parameters.get("query")
            year_low = parameters.get("year_low")
            year_high = parameters.get("year_high")
            pages = parameters.get("pages", 1)
            save_path = parameters.get("save_path")
            
            if not query:
                return {
                    "status": "error",
                    "output": "",
                    "error": "query is required"
                }
            
            # 爬取学术搜索结果（Google Scholar 在很多网络环境下会被封/重定向/403）
            # 如果失败，则回退到 DuckDuckGo 的 site:scholar.google.com 搜索（无需代理也更稳）
            try:
                all_content = await self._crawl_scholar(query, year_low, year_high, pages)
            except Exception as crawl_err:
                if DDGS_AVAILABLE:
                    ddg_query = f"site:scholar.google.com {query}"
                    results = DDGS().text(ddg_query, max_results=min(10, pages * 10))
                    lines = [
                        "# Google Scholar (fallback via DuckDuckGo)",
                        "",
                        f"- query: `{query}`",
                        f"- note: direct crawling failed: `{str(crawl_err)[:200]}`",
                        "",
                    ]
                    for i, r in enumerate(results or [], 1):
                        title = (r.get("title") or "").strip()
                        href = (r.get("href") or r.get("link") or "").strip()
                        body = (r.get("body") or "").strip()
                        if href:
                            lines.append(f"{i}. **{title or 'Untitled'}**")
                            lines.append(f"   - {href}")
                            if body:
                                lines.append(f"   - {body}")
                    all_content = "\n".join(lines) + "\n"
                else:
                    raise
            
            # 保存到文件
            if save_path:
                # 生成包含搜索参数的文件名
                from pathlib import Path
                save_path_obj = Path(save_path)
                safe_query = re.sub(r'[^\w\s-]', '', query).strip()
                safe_query = re.sub(r'[-\s]+', '_', safe_query)[:50]
                
                year_suffix = ""
                if year_low or year_high:
                    year_suffix = f"_y{year_low or 'X'}-{year_high or 'X'}"
                
                new_filename = f"{save_path_obj.stem}_{safe_query}{year_suffix}_p{pages}{save_path_obj.suffix}"
                final_save_path = str(save_path_obj.parent / new_filename)
                
                abs_save_path = get_abs_path(task_id, final_save_path)
                abs_save_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(abs_save_path, 'w', encoding='utf-8') as f:
                    f.write(all_content)
                
                output = f"结果保存在 {final_save_path}"
            else:
                output = all_content
            
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
    
    async def _crawl_scholar(self, query: str, year_low: int, year_high: int, pages: int) -> str:
        """爬取谷歌学术搜索结果"""
        base_url = "https://scholar.google.com/scholar"
        all_content = []
        
        browser_conf = BrowserConfig(headless=True, verbose=False)
        run_conf = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            for page in range(pages):
                start = page * 10
                
                params = {
                    "start": str(start),
                    "q": query,
                    "as_sdt": "0,5"
                }
                
                if year_low:
                    params["as_ylo"] = str(year_low)
                if year_high:
                    params["as_yhi"] = str(year_high)
                
                url = f"{base_url}?{urlencode(params)}"
                
                result = await crawler.arun(url, config=run_conf)
                
                markdown_attr = _get_field(result, "markdown", None)
                if markdown_attr:
                    markdown_text = (
                        _get_field(markdown_attr, "raw_markdown", None)
                        or _get_field(markdown_attr, "markdown", None)
                        or str(markdown_attr)
                    )
                    # 移除图片
                    markdown_text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", markdown_text)
                    all_content.append(f"--- Page {page + 1} ---\n{markdown_text}\n")
        
        return '\n'.join(all_content)


class WebSearchTool(BaseTool):
    """网络搜索工具 - 使用 DuckDuckGo"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        网络搜索（DuckDuckGo）
        
        Parameters:
            query (str): 搜索关键词
            max_results (int, optional): 最大结果数，默认10
            save_path (str, optional): 保存结果的相对路径（.md文件）
        """
        try:
            if not DDGS_AVAILABLE:
                return {
                    "status": "error",
                    "output": "",
                    "error": "ddgs not installed. Run: pip install ddgs"
                }
            
            query = parameters.get("query")
            max_results = parameters.get("max_results", 10)
            save_path = parameters.get("save_path")
            
            if not query:
                return {
                    "status": "error",
                    "output": "",
                    "error": "query is required"
                }
            
            # 使用 DuckDuckGo 搜索
            results = DDGS().text(query, max_results=max_results)
            
            # 格式化为 Markdown
            results_md = []
            results_md.append(f"# Search Results: {query}\n")
            results_md.append(f"Total: {len(results)} results\n")
            
            for i, result in enumerate(results, 1):
                title = result.get('title', 'No title')
                url = result.get('href', '')
                snippet = result.get('body', '')
                
                results_md.append(f"## {i}. {title}\n")
                results_md.append(f"**URL**: {url}\n")
                results_md.append(f"**Snippet**: {snippet}\n")
            
            results_text = '\n'.join(results_md)
            
            # 保存到文件
            if save_path:
                # 生成包含搜索参数的文件名
                from pathlib import Path
                save_path_obj = Path(save_path)
                safe_query = re.sub(r'[^\w\s-]', '', query).strip()
                safe_query = re.sub(r'[-\s]+', '_', safe_query)[:50]  # 限制长度
                
                new_filename = f"{save_path_obj.stem}_{safe_query}_n{max_results}{save_path_obj.suffix}"
                final_save_path = str(save_path_obj.parent / new_filename)
                
                abs_save_path = get_abs_path(task_id, final_save_path)
                abs_save_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(abs_save_path, 'w', encoding='utf-8') as f:
                    f.write(results_text)
                
                output = f"结果保存在 {final_save_path}"
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


class FileDownloadTool(BaseTool):
    """文件下载工具"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        从URL下载文件
        
        Parameters:
            url (str): 文件URL
            save_path (str): 保存的相对路径
        """
        try:
            url = parameters.get("url")
            save_path = parameters.get("save_path")
            
            abs_save_path = get_abs_path(task_id, save_path)
            abs_save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 下载文件
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            # 写入文件
            with open(abs_save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = abs_save_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            
            return {
                "status": "success",
                "output": f"Downloaded to {save_path} ({size_mb:.2f} MB)",
                "error": ""
            }
            
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }

