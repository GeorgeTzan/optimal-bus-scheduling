FROM python:3.13

WORKDIR /app

COPY pyproject.toml ./

RUN pip install uv && uv pip install --system fastapi uvicorn sentry-sdk[fastapi] sqlalchemy psycopg2-binary alembic python-jose[cryptography] passlib[bcrypt] python-multipart pydantic[email] python-dotenv ortools

# ENV PATH="/app/.venv/bin:$PATH"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]