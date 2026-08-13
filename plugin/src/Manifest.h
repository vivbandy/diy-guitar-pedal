#pragma once

// capture_id -> a local file on this machine. Captures are never referenced by path in a patch,
// so the manifest is the only place that binding lives.

#include <map>
#include <string>

namespace tone {

struct CaptureEntry {
  std::string id;
  std::string name;
  std::string file;
  std::string format = "nam";
  std::string category;
  bool includesCab = false;
};

class Manifest {
 public:
  void setRoot(std::string root) { root_ = std::move(root); }
  const std::string& root() const { return root_; }

  void add(const CaptureEntry& entry) { entries_[entry.id] = entry; }
  bool has(const std::string& id) const { return entries_.count(id) > 0; }
  std::size_t size() const { return entries_.size(); }

  const CaptureEntry* find(const std::string& id) const {
    const auto it = entries_.find(id);
    return it == entries_.end() ? nullptr : &it->second;
  }

  std::string resolve(const std::string& id) const {
    const CaptureEntry* entry = find(id);
    if (entry == nullptr) return {};
    if (entry->file.empty()) return {};
    if (entry->file.front() == '/' || root_.empty()) return entry->file;
    return root_.back() == '/' ? root_ + entry->file : root_ + "/" + entry->file;
  }

 private:
  std::string root_;
  std::map<std::string, CaptureEntry> entries_;
};

// Defined in ManifestJson.cpp — the only manifest code that depends on a JSON library.
bool loadManifestFromFile(const std::string& path, Manifest& out, std::string& error);

}  // namespace tone
