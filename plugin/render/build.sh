#!/usr/bin/env bash
# Build tone_render, the offline patch renderer. Needs only a C++20 compiler (clang or gcc); no
# cmake, Xcode, JUCE or iPlug2. NAM Core v0.5.3 (with Eigen and AudioDSPTools) is fetched into
# plugin/render/.deps on first run, or point NAM_CORE_DIR at an existing checkout, e.g. the one
# inside the NeuralAmpModelerPlugin fork.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="${here}/../src"
out="${here}/.build"
nam="${NAM_CORE_DIR:-${here}/.deps/NeuralAmpModelerCore}"
nam_tag="v0.5.3"

if [[ ! -f "${nam}/NAM/dsp.h" ]]; then
  echo "fetching NeuralAmpModelerCore ${nam_tag} into ${nam}"
  git clone -q --depth 1 --branch "${nam_tag}" https://github.com/sdatkinson/NeuralAmpModelerCore.git "${nam}"
  git -C "${nam}" submodule update -q --init --depth 1
fi

deps="${nam}/Dependencies"
mkdir -p "${out}"

"${CXX:-c++}" -std=c++20 -O3 -DNDEBUG -w \
  -I"${src}" -I"${nam}" -I"${deps}/eigen" -I"${deps}" -I"${deps}/nlohmann" -I"${deps}/AudioDSPTools/dsp" \
  -o "${out}/tone_render" \
  "${here}/render.cpp" \
  "${src}/PatchSpec.cpp" "${src}/ChainHost.cpp" "${src}/effects/Effects.cpp" \
  "${src}/PatchLoader.cpp" "${src}/ManifestJson.cpp" \
  "${nam}"/NAM/*.cpp "${nam}"/NAM/*/*.cpp \
  "${deps}/AudioDSPTools/dsp/ImpulseResponse.cpp" "${deps}/AudioDSPTools/dsp/dsp.cpp" \
  "${deps}/AudioDSPTools/dsp/wav.cpp"

echo "built ${out}/tone_render"
