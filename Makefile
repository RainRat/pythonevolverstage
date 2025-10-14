.PHONY: build test docker-build clean

build:
	cmake -S . -B build
	cmake --build build

test: build
	pytest tests/test_evolverstage.py tests/test_redcode_worker.py

docker-build:
	docker build -t corewar-evolver .

clean:
	rm -rf build redcode_worker.so redcode_worker.dll redcode_worker.dylib
