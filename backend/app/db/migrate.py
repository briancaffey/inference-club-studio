import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migrations():
    logger.info("Running database migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logger.info(result.stdout.strip())
    if result.returncode != 0:
        logger.error("Migration failed: %s", result.stderr.strip())
        sys.exit(1)
    logger.info("Migrations complete.")


if __name__ == "__main__":
    run_migrations()
