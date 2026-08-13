#pragma once

// Every effect obeys the same contract: configure on the message thread (prepare/setParams),
// then process() runs on the audio thread and must not allocate, lock, or touch the filesystem.

#include <algorithm>
#include <cmath>
#include <memory>
#include <string>

#include "../PatchSpec.h"

namespace tone {

class Effect {
 public:
  virtual ~Effect() = default;

  // Message thread. Allocation is allowed here and nowhere else.
  virtual void prepare(double sampleRate, int maxBlockSize) = 0;
  virtual void setParams(const NodeSpec& node) = 0;

  // Audio thread. Lock-free, allocation-free.
  virtual void process(float* left, float* right, int numSamples) = 0;

  virtual const char* typeName() const = 0;

  bool enabled = true;
};

using EffectPtr = std::unique_ptr<Effect>;

inline float clampf(float v, float lo, float hi) { return std::min(hi, std::max(lo, v)); }

inline double dbToGain(double db) { return std::pow(10.0, db / 20.0); }

}  // namespace tone
