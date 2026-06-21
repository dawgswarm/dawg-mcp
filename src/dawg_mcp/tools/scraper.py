"""Scraper tools: single-page scrape plus async crawl/batch jobs.

These call the DAWG scraper service over HTTP (no browser needed) via the
shared ``AsyncScraper`` held by the SessionManager.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import Context, FastMCP

from ..errors import map_errors


def _job_summary(job) -> dict:
    """Compact, agent-friendly view of a crawl/batch job."""
    return {
        "job_id": job.job_id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "errors": job.errors,
        "elapsed_ms": job.elapsed_ms,
        "pages": [
            {
                "url": p.url,
                "status_code": p.status_code,
                "content": p.content,
                "metadata": p.metadata,
                "error": p.error,
            }
            for p in job.pages
        ],
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    @map_errors
    async def scrape_page(
        ctx: Context,
        url: str,
        format: str = "markdown",
        main_content: bool = False,
        include_links: bool = False,
        render: Optional[str] = None,
        timeout_ms: int = 30000,
    ) -> dict:
        """Scrape a single URL and return extracted content (no browser session needed).

        Args:
            url: Target URL.
            format: "markdown" (default), "text", or "html".
            main_content: Strip nav/footer/ads boilerplate.
            include_links: Include discovered links in the result.
            render: None/"auto" (auto-detect, SPA fallback), "http" (no browser,
                cheapest), or "browser" (force full browser render).
            timeout_ms: Page fetch timeout in milliseconds.
        """
        scraper = ctx.request_context.lifespan_context["mgr"].scraper()
        result = await scraper.scrape(
            url,
            format=format,
            main_content=main_content,
            include_links=include_links,
            render=render,
            timeout_ms=timeout_ms,
        )
        return {
            "success": result.success,
            "url": result.url,
            "final_url": result.final_url,
            "status_code": result.status_code,
            "content": result.content,
            "metadata": result.metadata,
            "links": result.links,
            "error": result.error,
            "elapsed_ms": result.elapsed_ms,
        }

    @mcp.tool()
    @map_errors
    async def scrape_crawl(
        ctx: Context,
        url: str,
        format: str = "markdown",
        max_depth: int = 2,
        max_pages: int = 50,
        concurrency: int = 3,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        main_content: bool = False,
        timeout_ms: int = 30000,
    ) -> dict:
        """Start a crawl job from a seed URL. Returns immediately with a job_id.

        Poll progress with scrape_job_status(job_id). Use include_patterns /
        exclude_patterns (URL glob patterns) to scope the crawl.
        """
        scraper = ctx.request_context.lifespan_context["mgr"].scraper()
        job = await scraper.crawl(
            url,
            format=format,
            max_depth=max_depth,
            max_pages=max_pages,
            concurrency=concurrency,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            main_content=main_content,
            timeout_ms=timeout_ms,
        )
        return _job_summary(job)

    @mcp.tool()
    @map_errors
    async def scrape_batch(
        ctx: Context,
        urls: list[str],
        format: str = "markdown",
        concurrency: int = 5,
        main_content: bool = False,
        timeout_ms: int = 30000,
    ) -> dict:
        """Start a batch scrape over many URLs. Returns immediately with a job_id.

        Poll progress with scrape_job_status(job_id).
        """
        scraper = ctx.request_context.lifespan_context["mgr"].scraper()
        job = await scraper.batch(
            urls,
            format=format,
            concurrency=concurrency,
            main_content=main_content,
            timeout_ms=timeout_ms,
        )
        return _job_summary(job)

    @mcp.tool()
    @map_errors
    async def scrape_job_status(
        ctx: Context,
        job_id: str,
        wait: bool = False,
        wait_timeout: int = 120,
    ) -> dict:
        """Get the status (and any completed pages) of a crawl/batch job.

        Args:
            job_id: The job id returned by scrape_crawl / scrape_batch.
            wait: If true, block until the job leaves "running" (or wait_timeout).
            wait_timeout: Max seconds to wait when wait=true.
        """
        scraper = ctx.request_context.lifespan_context["mgr"].scraper()
        job = await scraper.get_job(job_id)
        if wait and job.status == "running":
            job = await job.wait(timeout=wait_timeout, poll_interval=2.0)
        return _job_summary(job)

    @mcp.tool()
    @map_errors
    async def scrape_cancel_job(ctx: Context, job_id: str) -> dict:
        """Cancel a running crawl/batch job."""
        scraper = ctx.request_context.lifespan_context["mgr"].scraper()
        await scraper.cancel_job(job_id)
        return {"job_id": job_id, "status": "cancelled"}
