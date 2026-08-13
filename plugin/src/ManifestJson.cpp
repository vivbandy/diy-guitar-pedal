#include <fstream>
#include <sstream>

#include <nlohmann/json.hpp>

#include "Manifest.h"

namespace tone {

bool loadManifestFromFile(const std::string& path, Manifest& out, std::string& error) {
  std::ifstream stream(path);
  if (!stream) {
    error = "cannot open manifest: " + path;
    return false;
  }

  std::ostringstream buffer;
  buffer << stream.rdbuf();

  nlohmann::json root;
  try {
    root = nlohmann::json::parse(buffer.str());
  } catch (const std::exception& exc) {
    error = std::string("manifest is not valid JSON: ") + exc.what();
    return false;
  }

  if (!root.contains("captures") || !root["captures"].is_array()) {
    error = "manifest has no `captures` array";
    return false;
  }

  out.setRoot(root.value("root", std::string()));
  for (const auto& item : root["captures"]) {
    CaptureEntry entry;
    entry.id = item.value("id", std::string());
    entry.name = item.value("name", std::string());
    entry.file = item.value("file", std::string());
    entry.format = item.value("format", std::string("nam"));
    entry.category = item.value("category", std::string());
    entry.includesCab = item.value("includes_cab", false);
    if (!entry.id.empty()) out.add(entry);
  }
  return true;
}

}  // namespace tone
