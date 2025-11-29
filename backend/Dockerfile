FROM python:3.13

WORKDIR /app

COPY pyproject.toml ./

RUN pip install uv && uv venv /app/.venv && . /app/.venv/bin/activate && uv pip install -e .

ENV PATH="/app/.venv/bin:$PATH"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]