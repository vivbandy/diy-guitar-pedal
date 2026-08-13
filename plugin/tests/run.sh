#!/usr/bin/env bash
# Build and run the framework-free plugin core tests. No cmake, no JUCE, no iPlug2.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="${here}/.build"
mkdir -p "${out}"

"${CXX:-clang++}" -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter \
  -o "${out}/test_core" \
  "${here}/test_core.cpp" \
  "${here}/../src/PatchSpec.cpp" \
  "${here}/../src/ChainHost.cpp" \
  "${here}/../src/effects/Effects.cpp"

"${out}/test_core"
