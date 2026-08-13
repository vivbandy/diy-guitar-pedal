#pragma once

// JSON -> PatchSpec. This and ManifestJson.cpp are the only files that need a JSON library;
// everything downstream works on plain structs, which is what lets the DSP layer be built and
// tested without the plugin framework.

#include <string>

#include "PatchSpec.h"

namespace tone {

struct LoadResult {
  PatchSpec patch;
  std::string error;
  bool ok() const { return error.empty(); }
};

LoadResult parsePatch(const std::string& json);
LoadResult loadPatchFromFile(const std::string& path);

}  // namespace tone
