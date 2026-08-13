#include "ChainHost.h"

#include "effects/Effects.h"

namespace tone {

void ChainHost::prepare(double sampleRate, int maxBlockSize) {
  sampleRate_ = sampleRate;
  maxBlockSize_ = maxBlockSize;

  if (ChainPtr chain = current()) {
    for (auto& effect : chain->effects) effect->prepare(sampleRate_, maxBlockSize_);
  }
}

BuildResult ChainHost::build(const PatchSpec& patch, const Manifest& manifest) {
  BuildResult result;

  if (!schemaVersionSupported(patch.schemaVersion)) {
    result.error = "Unsupported patch schema_version: " + patch.schemaVersion;
    return result;
  }

  auto chain = std::make_shared<Chain>();
  chain->name = patch.name;
  chain->inputGain = static_cast<float>(dbToGain(patch.inputGainDb));
  chain->outputGain = static_cast<float>(dbToGain(patch.outputGainDb));

  bool sawAmpHead = false;
  bool sawIrCab = false;

  for (int position = 0; position < static_cast<int>(patch.chain.size()); ++position) {
    const NodeSpec& node = patch.chain[static_cast<std::size_t>(position)];

    if (node.type == "nam_capture" || node.type == "ir_cab") {
      CaptureSlot slot;
      slot.position = position;
      slot.type = node.type;
      slot.captureId = node.captureId;
      slot.enabled = node.enabled;
      slot.levelDb = node.type == "ir_cab" ? node.param("level_db", 0.0)
                                           : node.param("output_level_db", 0.0);
      slot.localPath = manifest.resolve(node.captureId);

      if (slot.localPath.empty()) {
        result.warnings.push_back("capture '" + node.captureId +
                                  "' is not in the manifest — that node will be silent");
      }
      if (node.enabled && node.type == "ir_cab") sawIrCab = true;
      if (node.enabled && node.type == "nam_capture") {
        const CaptureEntry* entry = manifest.find(node.captureId);
        if (entry != nullptr && entry->category == "amp" && !entry->includesCab) sawAmpHead = true;
      }

      chain->captures.push_back(std::move(slot));
      continue;
    }

    EffectPtr effect = makeEffect(node.type);
    if (!effect) {
      result.warnings.push_back("unknown node type '" + node.type + "' — skipped");
      continue;
    }
    effect->enabled = node.enabled;
    effect->prepare(sampleRate_, maxBlockSize_);
    effect->setParams(node);

    chain->effects.push_back(std::move(effect));
    chain->positions.push_back(position);
  }

  if (chain->captures.empty()) {
    result.error = "Patch has no nam_capture or ir_cab node — there is no amp/cab core.";
    return result;
  }

  // The brain guarantees this; the plugin only warns, because refusing to make a sound is worse
  // than making a thin one.
  if (sawAmpHead && !sawIrCab) {
    result.warnings.push_back(
        "amp-head capture with no cab IR — this will sound thin and harsh");
  }

  result.chain = std::move(chain);
  return result;
}

void ChainHost::process(float* left, float* right, int numSamples) {
  const ChainPtr chain = current();
  if (!chain) return;

  for (int i = 0; i < numSamples; ++i) {
    left[i] *= chain->inputGain;
    if (right) right[i] *= chain->inputGain;
  }

  for (auto& effect : chain->effects) {
    if (effect->enabled) effect->process(left, right, numSamples);
  }

  for (int i = 0; i < numSamples; ++i) {
    left[i] *= chain->outputGain;
    if (right) right[i] *= chain->outputGain;
  }
}

}  // namespace tone
