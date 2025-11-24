FROM python:3.11-slim
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FIXED OpenAPI specs (IMPORTANT!)
# These specs have 989 fixes applied to handle null values
COPY fastmcp-fixed-specs/ ./fastmcp-fixed-specs/

# Copy the server code
COPY server.py .
RUN python -m py_compile server.py

# Expose port (adjust as needed)
EXPOSE 8000

CMD ["python", "server.py"]
