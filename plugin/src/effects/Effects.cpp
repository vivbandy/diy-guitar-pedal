#include "Effects.h"

namespace tone {

EffectPtr makeEffect(const std::string& type) {
  if (type == "drive") return std::make_unique<Drive>();
  if (type == "eq") return std::make_unique<Eq>();
  if (type == "compressor") return std::make_unique<Compressor>();
  if (type == "noise_gate") return std::make_unique<NoiseGate>();
  if (type == "delay") return std::make_unique<Delay>();
  if (type == "reverb") return std::make_unique<Reverb>();
  if (type == "modulation") return std::make_unique<Modulation>();
  if (type == "filter") return std::make_unique<Filter>();
  return nullptr;  // nam_capture and ir_cab are owned by the NAM/IR host, not this factory
}

}  // namespace tone
