// Standalone tests for the framework-free half of the plugin: chain building, the manifest
// binding, schema-version gating, and each effect's DSP stability. Needs no JUCE, no iPlug2, no
// JSON library and no cmake:
//
//   ./plugin/tests/run.sh
//
// PatchLoader/ManifestJson are excluded here because they need the baseline's nlohmann/json;
// they get exercised once the fork is in place.

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "../src/ChainHost.h"
#include "../src/Manifest.h"
#include "../src/PatchSpec.h"
#include "../src/effects/Effects.h"

namespace {

int failures = 0;
int checks = 0;

void check(bool condition, const std::string& what) {
  ++checks;
  if (!condition) {
    ++failures;
    std::printf("  FAIL  %s\n", what.c_str());
  }
}

tone::Manifest exampleManifest() {
  tone::Manifest manifest;
  manifest.setRoot("/tmp/captures");
  manifest.add({"hiwatt_dr103_clean", "Hiwatt DR103", "hiwatt_dr103_clean.nam", "nam", "amp",
                false});
  manifest.add({"fender_twin_fullrig_clean", "Fender Twin", "fender_twin_fullrig_clean.nam", "nam",
                "amp", true});
  manifest.add({"greenback_412_cab", "Greenback 412", "greenback_412_cab.wav", "wav_ir", "cab",
                false});
  return manifest;
}

tone::NodeSpec captureNode(const std::string& type, const std::string& id) {
  tone::NodeSpec node;
  node.type = type;
  node.captureId = id;
  return node;
}

tone::NodeSpec effectNode(const std::string& type, tone::ParamMap params = {},
                          tone::TextParamMap text = {}) {
  tone::NodeSpec node;
  node.type = type;
  node.params = std::move(params);
  node.textParams = std::move(text);
  return node;
}

bool finite(const std::vector<float>& buffer) {
  for (float v : buffer) {
    if (!std::isfinite(v) || std::fabs(v) > 100.0f) return false;
  }
  return true;
}

// --- tests ------------------------------------------------------------------

void testSchemaVersionGate() {
  check(tone::schemaVersionSupported("1.0"), "1.0 is supported");
  check(tone::schemaVersionSupported("1.7"), "a later minor of major 1 is supported");
  check(!tone::schemaVersionSupported("2.0"), "a future major is refused");
  check(!tone::schemaVersionSupported("banana"), "garbage is refused");
  check(tone::schemaMajor("1.0") == 1, "schemaMajor parses the major");
}

void testManifestResolvesLocalPaths() {
  const tone::Manifest manifest = exampleManifest();
  check(manifest.resolve("greenback_412_cab") == "/tmp/captures/greenback_412_cab.wav",
        "resolve joins root and file");
  check(manifest.resolve("nope").empty(), "unknown capture resolves to nothing");
  check(manifest.find("fender_twin_fullrig_clean")->includesCab, "full rig carries includes_cab");
}

void testChainBuildOrdersNodes() {
  tone::ChainHost host;
  host.prepare(48000.0, 512);

  tone::PatchSpec patch;
  patch.name = "gilmour";
  patch.chain = {
      effectNode("compressor"),
      effectNode("drive", {{"drive", 0.8}}, {{"style", "fuzz"}}),
      captureNode("nam_capture", "hiwatt_dr103_clean"),
      captureNode("ir_cab", "greenback_412_cab"),
      effectNode("delay", {{"time_ms", 460.0}}),
      effectNode("reverb"),
  };

  const tone::BuildResult result = host.build(patch, exampleManifest());
  check(result.ok(), "amp head + cab builds");
  check(result.warnings.empty(), "no warnings for a well-formed patch");
  check(result.chain->effects.size() == 4, "four effect nodes");
  check(result.chain->captures.size() == 2, "two capture slots");
  check(result.chain->positions == std::vector<int>({0, 1, 4, 5}), "effect positions preserved");
  check(result.chain->captures[0].localPath == "/tmp/captures/hiwatt_dr103_clean.nam",
        "capture slot resolved to a local path");
}

void testChainRejectsAndWarns() {
  tone::ChainHost host;
  host.prepare(48000.0, 512);
  const tone::Manifest manifest = exampleManifest();

  tone::PatchSpec future;
  future.schemaVersion = "2.0";
  future.chain = {captureNode("nam_capture", "hiwatt_dr103_clean")};
  check(!host.build(future, manifest).ok(), "a future schema major is rejected");

  tone::PatchSpec noCore;
  noCore.chain = {effectNode("delay")};
  check(!host.build(noCore, manifest).ok(), "a patch with no amp/cab core is rejected");

  tone::PatchSpec thin;
  thin.chain = {captureNode("nam_capture", "hiwatt_dr103_clean")};
  const tone::BuildResult thinResult = host.build(thin, manifest);
  check(thinResult.ok(), "an amp head without a cab still builds (warn, do not silence)");
  check(thinResult.warnings.size() == 1, "amp head without a cab warns");

  tone::PatchSpec fullRig;
  fullRig.chain = {captureNode("nam_capture", "fender_twin_fullrig_clean")};
  check(host.build(fullRig, manifest).warnings.empty(), "a full rig alone warns about nothing");

  tone::PatchSpec unknownCapture;
  unknownCapture.chain = {captureNode("nam_capture", "ghost_amp")};
  check(host.build(unknownCapture, manifest).warnings.size() == 1,
        "an unresolvable capture warns");

  tone::PatchSpec unknownType;
  unknownType.chain = {captureNode("nam_capture", "fender_twin_fullrig_clean"),
                       effectNode("teleporter")};
  const tone::BuildResult unknownResult = host.build(unknownType, manifest);
  check(unknownResult.ok() && unknownResult.chain->effects.empty(),
        "an unknown node type is skipped, not fatal");
}

void testDisabledNodesAreSkipped() {
  tone::ChainHost host;
  host.prepare(48000.0, 64);

  tone::NodeSpec gate = effectNode("noise_gate", {{"threshold_db", 0.0}});
  gate.enabled = false;

  tone::PatchSpec patch;
  patch.chain = {captureNode("nam_capture", "fender_twin_fullrig_clean"), gate};
  const tone::BuildResult result = host.build(patch, exampleManifest());
  host.publish(result.chain);

  std::vector<float> left(64, 0.5f);
  host.process(left.data(), nullptr, 64);
  check(left[32] == 0.5f, "a disabled effect does not touch the signal");
}

void testIoGainsApply() {
  tone::ChainHost host;
  host.prepare(48000.0, 16);

  tone::PatchSpec patch;
  patch.inputGainDb = 6.0;
  patch.outputGainDb = -6.0;
  patch.chain = {captureNode("nam_capture", "fender_twin_fullrig_clean")};

  host.publish(host.build(patch, exampleManifest()).chain);

  std::vector<float> left(16, 1.0f);
  host.process(left.data(), nullptr, 16);
  check(std::fabs(left[0] - 1.0f) < 1e-4f, "+6 dB in and -6 dB out cancel out");
}

void testProcessWithoutAPublishedChainIsSafe() {
  tone::ChainHost host;
  host.prepare(48000.0, 16);
  std::vector<float> left(16, 0.25f);
  host.process(left.data(), nullptr, 16);
  check(left[0] == 0.25f, "processing before a patch is loaded passes audio through");
}

void testEveryEffectIsStable() {
  const char* types[] = {"drive",  "eq",     "compressor", "noise_gate",
                         "delay",  "reverb", "modulation", "filter"};

  for (const char* type : types) {
    tone::EffectPtr effect = tone::makeEffect(type);
    check(effect != nullptr, std::string("factory makes a ") + type);
    if (!effect) continue;

    effect->prepare(48000.0, 256);

    tone::NodeSpec node = effectNode(type);
    if (std::string(type) == "eq") node.bands.push_back({800.0, 6.0, 1.2, "bell"});
    effect->setParams(node);

    std::vector<float> left(256), right(256);
    for (int block = 0; block < 8; ++block) {
      for (int i = 0; i < 256; ++i) {
        const float phase = static_cast<float>(block * 256 + i) / 48000.0f;
        left[i] = right[i] = 0.5f * std::sin(6.2831853f * 220.0f * phase);
      }
      effect->process(left.data(), right.data(), 256);
      check(finite(left), std::string(type) + " stays finite and bounded");
    }
  }
}

void testEffectsHandleMonoBuffers() {
  const char* types[] = {"drive",  "eq",     "compressor", "noise_gate",
                         "delay",  "reverb", "modulation", "filter"};
  for (const char* type : types) {
    tone::EffectPtr effect = tone::makeEffect(type);
    effect->prepare(44100.0, 128);
    effect->setParams(effectNode(type));

    std::vector<float> left(128, 0.1f);
    effect->process(left.data(), nullptr, 128);
    check(finite(left), std::string(type) + " handles a mono buffer");
  }
}

void testEqAppliesTheRequestedBoost() {
  tone::EffectPtr eq = tone::makeEffect("eq");
  eq->prepare(48000.0, 1024);

  tone::NodeSpec node = effectNode("eq");
  node.bands.push_back({1000.0, 12.0, 1.0, "bell"});
  eq->setParams(node);

  std::vector<float> left(4096);
  for (int i = 0; i < 4096; ++i) {
    left[i] = std::sin(6.2831853f * 1000.0f * static_cast<float>(i) / 48000.0f);
  }
  eq->process(left.data(), nullptr, 4096);

  float peak = 0.0f;
  for (int i = 2048; i < 4096; ++i) peak = std::max(peak, std::fabs(left[i]));
  check(peak > 2.0f, "a +12 dB bell at 1 kHz actually boosts 1 kHz");
}

void testDelayIsAudibleAndDoesNotRunAway() {
  tone::EffectPtr delay = tone::makeEffect("delay");
  delay->prepare(48000.0, 480);
  delay->setParams(effectNode("delay", {{"time_ms", 10.0}, {"feedback", 0.9}, {"mix", 0.5}}));

  std::vector<float> left(480, 0.0f);
  left[0] = 1.0f;
  delay->process(left.data(), nullptr, 480);

  // The first repeat lands 10 ms (480 samples) after the impulse, i.e. in the next block.
  std::fill(left.begin(), left.end(), 0.0f);
  delay->process(left.data(), nullptr, 480);

  float tail = 0.0f;
  for (int i = 0; i < 480; ++i) tail = std::max(tail, std::fabs(left[i]));
  check(tail > 0.0f, "the delay repeats are audible");

  for (int block = 0; block < 200; ++block) {
    std::fill(left.begin(), left.end(), 0.0f);
    delay->process(left.data(), nullptr, 480);
    if (!finite(left)) break;
  }
  check(finite(left), "0.9 feedback decays instead of exploding");
}

}  // namespace

int main() {
  testSchemaVersionGate();
  testManifestResolvesLocalPaths();
  testChainBuildOrdersNodes();
  testChainRejectsAndWarns();
  testDisabledNodesAreSkipped();
  testIoGainsApply();
  testProcessWithoutAPublishedChainIsSafe();
  testEveryEffectIsStable();
  testEffectsHandleMonoBuffers();
  testEqAppliesTheRequestedBoost();
  testDelayIsAudibleAndDoesNotRunAway();

  std::printf("%s  %d checks, %d failures\n", failures == 0 ? "PASS" : "FAIL", checks, failures);
  return failures == 0 ? 0 : 1;
}
