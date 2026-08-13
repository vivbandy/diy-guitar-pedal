cmake_minimum_required(VERSION 3.22)
project(tone_architect_plugin_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# The framework-free half: patch spec, chain host, effects. No JUCE, no iPlug2, no JSON.
# The fork links this and supplies the NAM/IR rendering plus the AU wrapper.
add_library(tone_core STATIC
    src/PatchSpec.cpp
    src/ChainHost.cpp
    src/effects/Effects.cpp
    src/transport/FilePatchSource.cpp
)
target_include_directories(tone_core PUBLIC src)
target_compile_options(tone_core PRIVATE -Wall -Wextra)

# The JSON layer is opt-in: it needs nlohmann/json, which the NeuralAmpModelerPlugin baseline
# already vendors. Enable it once this directory is building inside the fork.
option(TONE_WITH_JSON "Build the JSON patch/manifest loaders (needs nlohmann/json)" OFF)
if(TONE_WITH_JSON)
    target_sources(tone_core PRIVATE src/PatchLoader.cpp src/ManifestJson.cpp)
    find_package(nlohmann_json REQUIRED)
    target_link_libraries(tone_core PUBLIC nlohmann_json::nlohmann_json)
endif()

enable_testing()
add_executable(tone_core_tests tests/test_core.cpp)
target_link_libraries(tone_core_tests PRIVATE tone_core)
add_test(NAME tone_core_tests COMMAND tone_core_tests)
