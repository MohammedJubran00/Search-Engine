"""Read-only duplicate-upload verification snapshot, without document content."""
import argparse
import asyncio
import json
from sqlalchemy import text
from src.search_engine.database.database import SessionLocal, engine


async def snapshot(filename):
    async with SessionLocal() as session:
        rows = (await session.execute(text('''
            SELECT d.id::text AS document_id, s.status, s.generation,
              (SELECT count(*) FROM document_chunks c WHERE c.document_id=d.id) AS chunks,
              (SELECT count(*) FROM indexing_jobs j WHERE j.document_id=d.id) AS jobs
            FROM documents d LEFT JOIN document_index_states s ON s.document_id=d.id
            WHERE d.original_filename=:filename ORDER BY d.created_at
        '''), {'filename': filename})).mappings().all()
        print(json.dumps([dict(row) for row in rows], indent=2))
    await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    asyncio.run(snapshot(parser.parse_args().filename))
