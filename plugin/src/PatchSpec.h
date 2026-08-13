#pragma once

// The plugin-side mirror of schema/patch.schema.json, deliberately free of any JSON or
// framework dependency so the DSP layer can be built and tested on its own. PatchLoader is the
// only translation unit that knows about JSON.

#include <map>
#include <string>
#include <vector>

namespace tone {

constexpr int kSupportedSchemaMajor = 1;

using ParamMap = std::map<std::string, double>;
using TextParamMap = std::map<std::string, std::string>;

struct EqBandSpec {
  double freqHz = 1000.0;
  double gainDb = 0.0;
  double q = 0.7;
  std::string shape = "bell";
};

struct NodeSpec {
  std::string type;
  bool enabled = true;
  std::string label;
  std::string captureId;
  ParamMap params;
  TextParamMap textParams;
  std::vector<EqBandSpec> bands;

  double param(const std::string& key, double fallback) const {
    const auto it = params.find(key);
    return it == params.end() ? fallback : it->second;
  }

  std::string text(const std::string& key, const std::string& fallback) const {
    const auto it = textParams.find(key);
    return it == textParams.end() ? fallback : it->second;
  }
};

struct PatchSpec {
  std::string schemaVersion = "1.0";
  std::string name;
  std::string description;
  double inputGainDb = 0.0;
  double outputGainDb = 0.0;
  std::vector<NodeSpec> chain;
};

// "1.0" -> 1. Returns -1 when the string is not a version we can parse at all.
int schemaMajor(const std::string& version);

// Prime Directive: the plugin refuses a patch from a future major it cannot represent.
inline bool schemaVersionSupported(const std::string& version) {
  const int major = schemaMajor(version);
  return major >= 0 && major <= kSupportedSchemaMajor;
}

}  // namespace tone
