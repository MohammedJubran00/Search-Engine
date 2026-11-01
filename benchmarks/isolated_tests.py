"""Run normal pytest in a private schema, invisible to public indexing workers."""
import asyncio
import sys
import pytest
from benchmarks.live_gemini import isolate_database
from src.search_engine.core.config import settings


def main():
    teardown = isolate_database(settings.database_url)
    try:
        return pytest.main(sys.argv[1:] or ['-q'])
    finally:
        asyncio.run(teardown())


if __name__ == '__main__':
    raise SystemExit(main())
