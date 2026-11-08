FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev
COPY main.py config.py monitor.py state.py railway_entry.py ./
CMD ["/app/.venv/bin/python", "railway_entry.py"]
