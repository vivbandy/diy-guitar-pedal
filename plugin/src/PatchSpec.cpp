#include "PatchSpec.h"

#include <cctype>

namespace tone {

int schemaMajor(const std::string& version) {
  if (version.empty()) return -1;

  std::size_t i = 0;
  int major = 0;
  while (i < version.size() && std::isdigit(static_cast<unsigned char>(version[i]))) {
    major = major * 10 + (version[i] - '0');
    ++i;
  }
  if (i == 0) return -1;
  if (i < version.size() && version[i] != '.') return -1;
  return major;
}

}  // namespace tone
