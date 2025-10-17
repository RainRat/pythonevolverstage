FROM python:3.11-slim

# Install build tools and dependencies for the C++ worker and pMARS emulator
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ cmake make libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Build the optional C++ worker library using CMake and compile the pMARS emulator
RUN mkdir -p build \
    && cd build \
    && cmake .. \
    && cmake --build . \
    && cp ../redcode_worker.so /usr/local/lib/ \
    && make -C ../pMars/src \
    && cp ../pMars/src/pmars /usr/local/bin/pmars

# Default command runs the evolver
CMD ["python", "evolverstage.py"]
