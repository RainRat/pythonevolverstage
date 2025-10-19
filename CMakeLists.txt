cmake_minimum_required(VERSION 3.10)
project(RedcodeWorker)

set(default_build_type "RelWithDebInfo")
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  message(STATUS "Setting build type to '${default_build_type}' as none was specified.")
  set(CMAKE_BUILD_TYPE "${default_build_type}" CACHE STRING "Choose the type of build." FORCE)
  set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release" "RelWithDebInfo" "MinSizeRel")
endif()

add_library(redcode_worker SHARED redcode-worker.cpp)

# On Windows, CMake adds a "lib" prefix by default, which we don't want for ctypes.
# Configure the output so that the shared library is emitted in the project root
# without a "lib" prefix, matching the expectations of the Python loader.
set_target_properties(redcode_worker PROPERTIES
  PREFIX ""
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
  ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
)
