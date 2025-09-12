cmake_minimum_required(VERSION 3.10)
project(RedcodeWorker)

add_library(redcode_worker SHARED redcode-worker.cpp)

# On Windows, CMake adds a "lib" prefix by default, which we don't want for ctypes.
# This will name the output redcode_worker.dll on Windows.
# On Linux/macOS, it will be redcode_worker.so or redcode_worker.dylib.
set_target_properties(redcode_worker PROPERTIES PREFIX "")
