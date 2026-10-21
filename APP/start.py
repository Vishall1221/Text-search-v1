"""Start the local API using root config/.env."""

import uvicorn

from config.settings import settings


if __name__ == "__main__":
    uvicorn.run("APP.backend.main:app", host=settings.api_host, port=settings.api_port)
