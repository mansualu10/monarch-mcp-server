FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt requirements-azure.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-azure.txt

# Copy source code
COPY pyproject.toml ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "monarch_mcp_server.remote_server"]
