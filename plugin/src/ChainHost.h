#pragma once

// Owns the ordered chain. Building a chain allocates, so it happens on the message thread; the
// audio thread only ever reads the currently-published chain through an atomic pointer.

#include <atomic>
#include <memory>
#include <string>
#include <vector>

#include "Manifest.h"
#include "PatchSpec.h"
#include "effects/Effect.h"

namespace tone {

// A node the plugin's own NAM/IR host is responsible for loading. ChainHost records where it sits
// in the chain so the host can splice its processing in at the right point.
struct CaptureSlot {
  int position = 0;
  std::string type;  // "nam_capture" or "ir_cab"
  std::string captureId;
  std::string localPath;
  double levelDb = 0.0;
  bool enabled = true;
};

struct Chain {
  std::vector<EffectPtr> effects;      // parallel to `positions`
  std::vector<int> positions;
  std::vector<CaptureSlot> captures;
  float inputGain = 1.0f;
  float outputGain = 1.0f;
  std::string name;
};

using ChainPtr = std::shared_ptr<Chain>;

struct BuildResult {
  ChainPtr chain;
  std::vector<std::string> warnings;
  std::string error;  // non-empty means nothing was built
  bool ok() const { return error.empty(); }
};

class ChainHost {
 public:
  // --- message thread -------------------------------------------------------
  void prepare(double sampleRate, int maxBlockSize);
  BuildResult build(const PatchSpec& patch, const Manifest& manifest);
  void publish(ChainPtr chain) { std::atomic_store(&current_, std::move(chain)); }

  // --- audio thread ---------------------------------------------------------
  // Runs the effect nodes only. The caller interleaves NAM/IR rendering using the CaptureSlot
  // positions, because those live in the forked plugin's own model host.
  void process(float* left, float* right, int numSamples);

  ChainPtr current() const { return std::atomic_load(&current_); }

 private:
  ChainPtr current_;
  double sampleRate_ = 48000.0;
  int maxBlockSize_ = 512;
};

}  // namespace tone
