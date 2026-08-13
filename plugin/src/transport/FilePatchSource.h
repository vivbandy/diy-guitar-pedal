#pragma once

// Phase 3: poll a known path and reload when it changes. The brain writes atomically
// (temp file + rename), so a size/mtime change always means a complete file — there is no
// partially-written patch to observe.
//
// Polling runs on a timer on the message thread. Nothing here is called from processBlock.

#include <cstdint>
#include <functional>
#include <string>

namespace tone {

class FilePatchSource {
 public:
  using Callback = std::function<void(const std::string& path)>;

  void setPath(std::string path) {
    path_ = std::move(path);
    lastSize_ = 0;
    lastModified_ = 0;
  }

  const std::string& path() const { return path_; }
  void onChanged(Callback callback) { callback_ = std::move(callback); }

  // Call from a message-thread timer (~250 ms is plenty). Returns true when it fired.
  bool poll();

 private:
  std::string path_;
  std::uint64_t lastSize_ = 0;
  std::int64_t lastModified_ = 0;
  Callback callback_;
};

}  // namespace tone
