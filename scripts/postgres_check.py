"""Run the same API integration suite against a temporary real PostgreSQL database."""
import os
import subprocess
import sys
from pathlib import Path

import embedded_postgres
import psycopg


def main():
    data = Path("runtime/postgres-verification").resolve()
    data.mkdir(parents=True, exist_ok=True)
    with embedded_postgres.get_server(data, cleanup_mode="stop") as server:
        uri = server.get_uri()
        with psycopg.connect(uri, autocommit=True) as connection:
            version = connection.execute("SELECT version()").fetchone()[0]
            print(version, flush=True)
            import uuid
            database = "fccs_test_" + uuid.uuid4().hex
            from psycopg import sql
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        database_uri = uri.rsplit("/", 1)[0] + "/" + database
        env = dict(os.environ, TEST_DATABASE_URL=database_uri.replace("postgresql://", "postgresql+psycopg://", 1))
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/test_api.py", "-q", "--junitxml=reports/postgres.xml"], env=env, check=False)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
