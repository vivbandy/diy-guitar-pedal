#include "PatchLoader.h"

#include <fstream>
#include <sstream>

// nlohmann/json ships with the NeuralAmpModelerPlugin baseline (iPlug2 dependency tree).
#include <nlohmann/json.hpp>

namespace tone {
namespace {

using nlohmann::json;

void readParams(const json& params, NodeSpec& node) {
  for (auto it = params.begin(); it != params.end(); ++it) {
    if (it.key() == "capture_id") {
      node.captureId = it.value().get<std::string>();
    } else if (it.value().is_number()) {
      node.params[it.key()] = it.value().get<double>();
    } else if (it.value().is_string()) {
      node.textParams[it.key()] = it.value().get<std::string>();
    } else if (it.key() == "bands" && it.value().is_array()) {
      for (const auto& band : it.value()) {
        EqBandSpec spec;
        spec.freqHz = band.value("freq_hz", 1000.0);
        spec.gainDb = band.value("gain_db", 0.0);
        spec.q = band.value("q", 0.7);
        spec.shape = band.value("shape", std::string("bell"));
        node.bands.push_back(spec);
      }
    }
  }
}

}  // namespace

LoadResult parsePatch(const std::string& text) {
  LoadResult result;

  json root;
  try {
    root = json::parse(text);
  } catch (const std::exception& exc) {
    result.error = std::string("patch is not valid JSON: ") + exc.what();
    return result;
  }

  if (!root.is_object() || !root.contains("chain") || !root["chain"].is_array()) {
    result.error = "patch has no `chain` array";
    return result;
  }

  PatchSpec patch;
  patch.schemaVersion = root.value("schema_version", std::string("1.0"));
  if (!schemaVersionSupported(patch.schemaVersion)) {
    result.error = "unsupported patch schema_version: " + patch.schemaVersion;
    return result;
  }

  patch.name = root.value("name", std::string("Untitled"));
  patch.description = root.value("description", std::string());

  if (root.contains("io") && root["io"].is_object()) {
    patch.inputGainDb = root["io"].value("input_gain_db", 0.0);
    patch.outputGainDb = root["io"].value("output_gain_db", 0.0);
  }

  for (const auto& item : root["chain"]) {
    if (!item.is_object() || !item.contains("type")) continue;

    NodeSpec node;
    node.type = item["type"].get<std::string>();
    node.enabled = item.value("enabled", true);
    node.label = item.value("label", std::string());
    if (item.contains("params") && item["params"].is_object()) readParams(item["params"], node);

    patch.chain.push_back(std::move(node));
  }

  if (patch.chain.empty()) {
    result.error = "patch chain is empty";
    return result;
  }

  result.patch = std::move(patch);
  return result;
}

LoadResult loadPatchFromFile(const std::string& path) {
  std::ifstream stream(path);
  if (!stream) {
    LoadResult result;
    result.error = "cannot open patch file: " + path;
    return result;
  }
  std::ostringstream buffer;
  buffer << stream.rdbuf();
  return parsePatch(buffer.str());
}

}  // namespace tone
