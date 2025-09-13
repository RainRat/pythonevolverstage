FROM python:3.11-slim

# Install build tools for the C++ worker
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ cmake make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Build the optional C++ worker library
RUN g++ -std=c++17 -shared -fPIC redcode-worker.cpp -o redcode_worker.so

# Default command runs the evolver
CMD ["python", "evolverstage.py"]
