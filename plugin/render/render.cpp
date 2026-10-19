// tone_render: play a dry guitar recording through a patch.json offline and write the result.
//
//   tone_render --patch out/patch.json --manifest captures.manifest.json --in di.wav --out wet.wav
//
// It runs the same pieces the plugin does, in chain order: our effects (plugin/src), NAM Core for
// nam_capture nodes, and AudioDSPTools' ImpulseResponse for ir_cab nodes, which is the exact IR
// code the NeuralAmpModeler plugin uses. That makes a render a faithful preview of what the AU will
// play, and it's what the tone-matching tools compare against a reference recording.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "ChainHost.h"
#include "Manifest.h"
#include "PatchLoader.h"

#include "ImpulseResponse.h"
#include "NAM/dsp.h"
#include "NAM/get_dsp.h"
#include "wav.h"

namespace {

constexpr int kBlock = 512;
constexpr double kTargetLoudnessDb = -18.0;

using Processor = std::function<void(float* left, float* right, int n)>;

bool writeWavStereoFloat(const std::string& path, const std::vector<float>& left,
                         const std::vector<float>& right, double sampleRate) {
  std::ofstream out(path, std::ios::binary);
  if (!out) return false;

  const uint16_t channels = 2;
  const uint32_t rate = static_cast<uint32_t>(sampleRate);
  const uint32_t dataSize = static_cast<uint32_t>(left.size() * channels * sizeof(float));
  const uint32_t riffSize = 36 + dataSize;
  const uint32_t fmtSize = 16;
  const uint16_t format = 3;  // IEEE float
  const uint32_t byteRate = rate * channels * sizeof(float);
  const uint16_t blockAlign = channels * sizeof(float);
  const uint16_t bits = 32;

  out.write("RIFF", 4);
  out.write(reinterpret_cast<const char*>(&riffSize), 4);
  out.write("WAVEfmt ", 8);
  out.write(reinterpret_cast<const char*>(&fmtSize), 4);
  out.write(reinterpret_cast<const char*>(&format), 2);
  out.write(reinterpret_cast<const char*>(&channels), 2);
  out.write(reinterpret_cast<const char*>(&rate), 4);
  out.write(reinterpret_cast<const char*>(&byteRate), 4);
  out.write(reinterpret_cast<const char*>(&blockAlign), 2);
  out.write(reinterpret_cast<const char*>(&bits), 2);
  out.write("data", 4);
  out.write(reinterpret_cast<const char*>(&dataSize), 4);
  for (std::size_t i = 0; i < left.size(); ++i) {
    out.write(reinterpret_cast<const char*>(&left[i]), sizeof(float));
    out.write(reinterpret_cast<const char*>(&right[i]), sizeof(float));
  }
  return out.good();
}

// Captures are mono devices: sum to mono, run, and write the result to both channels.
// `drive` is the node's input_level_db: how hard the capture is hit, which changes how much a
// non-linear model breaks up. It's the one "knob" a snapshot capture really has.
Processor namProcessor(std::shared_ptr<nam::DSP> model, float drive, float level) {
  auto in = std::make_shared<std::vector<NAM_SAMPLE>>(kBlock);
  auto out = std::make_shared<std::vector<NAM_SAMPLE>>(kBlock);
  return [model, in, out, drive, level](float* left, float* right, int n) {
    for (int i = 0; i < n; ++i) (*in)[i] = drive * (right ? 0.5f * (left[i] + right[i]) : left[i]);
    NAM_SAMPLE* inPtr = in->data();
    NAM_SAMPLE* outPtr = out->data();
    model->process(&inPtr, &outPtr, n);
    for (int i = 0; i < n; ++i) {
      left[i] = static_cast<float>((*out)[i]) * level;
      if (right) right[i] = left[i];
    }
  };
}

Processor irProcessor(std::shared_ptr<dsp::ImpulseResponse> ir, float level) {
  auto in = std::make_shared<std::vector<DSP_SAMPLE>>(kBlock);
  return [ir, in, level](float* left, float* right, int n) {
    for (int i = 0; i < n; ++i) (*in)[i] = right ? 0.5f * (left[i] + right[i]) : left[i];
    DSP_SAMPLE* inPtr = in->data();
    DSP_SAMPLE** result = ir->Process(&inPtr, 1, static_cast<size_t>(n));
    for (int i = 0; i < n; ++i) {
      left[i] = static_cast<float>(result[0][i]) * level;
      if (right) right[i] = left[i];
    }
  };
}

void usage() {
  std::cerr << "usage: tone_render --patch PATCH.json --manifest MANIFEST.json --in DI.wav "
               "--out OUT.wav [--tail SECONDS] [--no-normalize]\n"
               "  Capture paths resolve against the manifest's `root`, relative to the manifest.\n"
               "  --tail adds silence so delay/reverb can ring out (default 2).\n"
               "  NAM models are levelled to -18 dB like the plugin's Normalize; --no-normalize skips it.\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::string patchPath, manifestPath, inPath, outPath;
  double tailSeconds = 2.0;
  bool normalize = true;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : std::string(); };
    if (arg == "--patch") patchPath = next();
    else if (arg == "--manifest") manifestPath = next();
    else if (arg == "--in") inPath = next();
    else if (arg == "--out") outPath = next();
    else if (arg == "--tail") tailSeconds = std::atof(next().c_str());
    else if (arg == "--no-normalize") normalize = false;
    else if (arg == "-h" || arg == "--help") { usage(); return 0; }
    else { std::cerr << "unknown argument: " << arg << "\n"; usage(); return 2; }
  }
  if (patchPath.empty() || manifestPath.empty() || inPath.empty() || outPath.empty()) {
    usage();
    return 2;
  }

  const tone::LoadResult loaded = tone::loadPatchFromFile(patchPath);
  if (!loaded.ok()) { std::cerr << loaded.error << "\n"; return 1; }

  tone::Manifest manifest;
  std::string error;
  if (!tone::loadManifestFromFile(manifestPath, manifest, error)) { std::cerr << error << "\n"; return 1; }
  // A relative root means "next to the manifest", the same way the brain resolves it.
  const auto manifestDir = std::filesystem::absolute(manifestPath).parent_path();
  if (manifest.root().empty() || manifest.root().front() != '/') {
    manifest.setRoot((manifestDir / manifest.root()).lexically_normal().string());
  }

  std::vector<float> dry;
  double sampleRate = 0.0;
  const auto wavResult = dsp::wav::Load(inPath.c_str(), dry, sampleRate);
  if (wavResult != dsp::wav::LoadReturnCode::SUCCESS) {
    std::cerr << "cannot read " << inPath << ": " << dsp::wav::GetMsgForLoadReturnCode(wavResult) << "\n";
    return 1;
  }

  tone::ChainHost host;
  host.prepare(sampleRate, kBlock);
  const tone::BuildResult built = host.build(loaded.patch, manifest);
  for (const auto& warning : built.warnings) std::cerr << "warning: " << warning << "\n";
  if (!built.ok()) { std::cerr << built.error << "\n"; return 1; }
  const tone::Chain& chain = *built.chain;

  // One processor per chain position, in order. ChainHost::process only runs the effects, because
  // in the plugin the captures live in the fork's model host; offline we splice them in here.
  std::vector<std::pair<int, Processor>> stages;
  for (std::size_t k = 0; k < chain.effects.size(); ++k) {
    tone::Effect* effect = chain.effects[k].get();
    if (!effect->enabled) continue;
    stages.emplace_back(chain.positions[k],
                        [effect](float* l, float* r, int n) { effect->process(l, r, n); });
  }
  for (const auto& slot : chain.captures) {
    if (!slot.enabled || slot.localPath.empty()) continue;
    if (!std::filesystem::exists(slot.localPath)) {
      std::cerr << "warning: " << slot.captureId << ": file not found at " << slot.localPath
                << " (run `make t3k-download`); that node is bypassed\n";
      continue;
    }
    float level = static_cast<float>(tone::dbToGain(slot.levelDb));
    if (slot.type == "nam_capture") {
      std::shared_ptr<nam::DSP> model = nam::get_dsp(std::filesystem::path(slot.localPath));
      if (!model) { std::cerr << "cannot load model " << slot.localPath << "\n"; return 1; }
      const double expected = model->GetExpectedSampleRate();
      if (expected > 0 && std::abs(expected - sampleRate) > 0.5) {
        std::cerr << slot.captureId << " expects " << expected << " Hz but " << inPath << " is "
                  << sampleRate << " Hz; resample the input first\n";
        return 1;
      }
      // Same levelling as the NeuralAmpModeler plugin's Normalize, so captures recorded at very
      // different volumes hit the next stage at a comparable level.
      if (normalize && model->HasLoudness()) {
        level *= static_cast<float>(tone::dbToGain(kTargetLoudnessDb - model->GetLoudness()));
      }
      model->ResetAndPrewarm(sampleRate, kBlock);
      const tone::NodeSpec& node = loaded.patch.chain[static_cast<std::size_t>(slot.position)];
      const float drive = static_cast<float>(tone::dbToGain(node.param("input_level_db", 0.0)));
      stages.emplace_back(slot.position, namProcessor(model, drive, level));
    } else {
      auto ir = std::make_shared<dsp::ImpulseResponse>(slot.localPath.c_str(), sampleRate);
      if (ir->GetWavState() != dsp::wav::LoadReturnCode::SUCCESS) {
        std::cerr << "cannot load IR " << slot.localPath << "\n";
        return 1;
      }
      stages.emplace_back(slot.position, irProcessor(ir, level));
    }
  }
  std::stable_sort(stages.begin(), stages.end(),
                   [](const auto& a, const auto& b) { return a.first < b.first; });

  const std::size_t total = dry.size() + static_cast<std::size_t>(tailSeconds * sampleRate);
  std::vector<float> left(total, 0.0f), right(total, 0.0f);
  std::copy(dry.begin(), dry.end(), left.begin());
  std::copy(dry.begin(), dry.end(), right.begin());

  for (std::size_t start = 0; start < total; start += kBlock) {
    const int n = static_cast<int>(std::min<std::size_t>(kBlock, total - start));
    float* l = left.data() + start;
    float* r = right.data() + start;
    for (int i = 0; i < n; ++i) { l[i] *= chain.inputGain; r[i] *= chain.inputGain; }
    for (auto& stage : stages) stage.second(l, r, n);
    for (int i = 0; i < n; ++i) { l[i] *= chain.outputGain; r[i] *= chain.outputGain; }
  }

  float peak = 0.0f;
  for (std::size_t i = 0; i < total; ++i) peak = std::max({peak, std::fabs(left[i]), std::fabs(right[i])});
  if (!writeWavStereoFloat(outPath, left, right, sampleRate)) {
    std::cerr << "cannot write " << outPath << "\n";
    return 1;
  }
  std::cerr << "OK wrote " << outPath << " (" << stages.size() << " stages, "
            << total / sampleRate << " s, peak " << 20.0 * std::log10(std::max(peak, 1e-9f))
            << " dBFS)\n";
  return 0;
}
