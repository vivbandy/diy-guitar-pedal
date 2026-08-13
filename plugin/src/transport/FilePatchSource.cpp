#include "FilePatchSource.h"

#include <sys/stat.h>

namespace tone {

bool FilePatchSource::poll() {
  if (path_.empty()) return false;

  struct stat info {};
  if (::stat(path_.c_str(), &info) != 0) return false;

  const auto size = static_cast<std::uint64_t>(info.st_size);
  const auto modified = static_cast<std::int64_t>(info.st_mtime);
  if (size == lastSize_ && modified == lastModified_) return false;

  const bool first = lastModified_ == 0 && lastSize_ == 0;
  lastSize_ = size;
  lastModified_ = modified;
  if (first) return false;

  if (callback_) callback_(path_);
  return true;
}

}  // namespace tone
