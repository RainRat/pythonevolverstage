FROM python:3.11-slim

# Install build tools for the C++ worker
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ cmake make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Build the optional C++ worker library using CMake
RUN mkdir -p build \
    && cd build \
    && cmake .. \
    && cmake --build .

# Default command runs the evolver
CMD ["python", "evolverstage.py"]
