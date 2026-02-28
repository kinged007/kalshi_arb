# Use a lightweight python image
FROM python:3.12-slim

# Install uv directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv sync (frozen ensures it uses the lock file exactly)
RUN uv sync --frozen

# Copy the rest of the application files
COPY . .

# Ensure standard output streams aren't buffered so logs show immediately in Docker
ENV PYTHONUNBUFFERED=1

# Command to run on startup. 
# Pre-filled with the arguments you requested.
CMD ["uv", "run", "python", "kalshi_arb.py", "watch", "--max-hours", "0.5", "--reset-int", "0.25", "--stake", "1", "--trade"]
