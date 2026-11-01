cmake_minimum_required(VERSION 3.20)
project(FreestyleExportReference LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
find_package(Torch REQUIRED)
add_executable(freestyle-export-reference reference.cpp)
set(GIGA "${GIGALEARN_SOURCE}/GigaLearnCPP")
target_include_directories(freestyle-export-reference PRIVATE "${REPO_ROOT}" "${GIGA}/src/public"
 "${GIGA}/src/private" "${GIGA}/libsrc/json" "${GIGA}/RLGymCPP/src" "${GIGA}/RLGymCPP/thread_pool"
 "${GIGA}/pybind11/include" "${PYTHON_INCLUDE_DIR}")
target_link_libraries(freestyle-export-reference PRIVATE
 "${FREESTYLE_BUILD}/giga/libGigaLearnCPP.so" "${FREESTYLE_BUILD}/giga/RLGymCPP/libRLGymCPP.a"
 "${FREESTYLE_BUILD}/giga/RLGymCPP/RocketSim/libRocketSim.a" "${TORCH_LIBRARIES}" "${PYTHON_LIBRARY}")
separate_arguments(TORCH_OPTIONS NATIVE_COMMAND "${TORCH_CXX_FLAGS}")
target_compile_options(freestyle-export-reference PRIVATE ${TORCH_OPTIONS})
