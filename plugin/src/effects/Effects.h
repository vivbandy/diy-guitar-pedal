#pragma once

// Effects in the priority order from docs/05-PLUGIN-SPEC.md:
// drive -> eq -> compressor -> delay -> reverb -> modulation -> noise_gate -> filter.
//
// Every buffer these need is sized in prepare() on the message thread; process() only reads and
// writes into already-owned storage.

#include <vector>

#include "Biquad.h"
#include "Effect.h"

namespace tone {

class Drive : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    tilt_.setHighShelf(sampleRate, 1200.0, 0.7, 0.0);
    sampleRate_ = sampleRate;
  }

  void setParams(const NodeSpec& node) override {
    style_ = node.text("style", "overdrive");
    drive_ = static_cast<float>(node.param("drive", 0.5));
    level_ = static_cast<float>(node.param("level", 0.5));
    const double tone = node.param("tone", 0.5);
    tilt_.setHighShelf(sampleRate_, 1200.0, 0.7, (tone - 0.5) * 18.0);
    gain_ = 1.0f + drive_ * driveRange();
  }

  void process(float* left, float* right, int n) override {
    for (int i = 0; i < n; ++i) {
      left[i] = tilt_.process(0, shape(left[i] * gain_)) * level_ * 2.0f;
      if (right) right[i] = tilt_.process(1, shape(right[i] * gain_)) * level_ * 2.0f;
    }
  }

  const char* typeName() const override { return "drive"; }

 private:
  float driveRange() const {
    if (style_ == "boost") return 8.0f;
    if (style_ == "distortion") return 60.0f;
    if (style_ == "fuzz") return 120.0f;
    return 24.0f;
  }

  float shape(float x) const {
    if (style_ == "fuzz") {
      // Asymmetric hard clip: the ragged, compressed edge a Muff-style circuit has.
      return clampf(x, -0.6f, 0.9f);
    }
    return std::tanh(x);
  }

  std::string style_ = "overdrive";
  float drive_ = 0.5f, level_ = 0.5f, gain_ = 1.0f;
  double sampleRate_ = 48000.0;
  Biquad tilt_;
};

class Eq : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    for (auto& b : filters_) b.reset();
  }

  void setParams(const NodeSpec& node) override {
    active_ = 0;
    for (const auto& band : node.bands) {
      if (active_ >= kMaxBands) break;
      auto& f = filters_[active_];
      if (band.shape == "low_shelf") {
        f.setLowShelf(sampleRate_, band.freqHz, band.q, band.gainDb);
      } else if (band.shape == "high_shelf") {
        f.setHighShelf(sampleRate_, band.freqHz, band.q, band.gainDb);
      } else {
        f.setBell(sampleRate_, band.freqHz, band.q, band.gainDb);
      }
      ++active_;
    }
  }

  void process(float* left, float* right, int n) override {
    for (int b = 0; b < active_; ++b) {
      for (int i = 0; i < n; ++i) {
        left[i] = filters_[b].process(0, left[i]);
        if (right) right[i] = filters_[b].process(1, right[i]);
      }
    }
  }

  const char* typeName() const override { return "eq"; }

 private:
  static constexpr int kMaxBands = 8;  // matches the schema's maxItems
  Biquad filters_[kMaxBands];
  int active_ = 0;
  double sampleRate_ = 48000.0;
};

class Compressor : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    env_[0] = env_[1] = 0.0f;
  }

  void setParams(const NodeSpec& node) override {
    thresholdDb_ = static_cast<float>(node.param("threshold_db", -18.0));
    ratio_ = static_cast<float>(node.param("ratio", 4.0));
    makeup_ = static_cast<float>(dbToGain(node.param("makeup_db", 0.0)));
    attack_ = coeff(node.param("attack_ms", 10.0));
    release_ = coeff(node.param("release_ms", 100.0));
  }

  void process(float* left, float* right, int n) override {
    for (int i = 0; i < n; ++i) {
      left[i] = apply(0, left[i]);
      if (right) right[i] = apply(1, right[i]);
    }
  }

  const char* typeName() const override { return "compressor"; }

 private:
  float coeff(double ms) const {
    return static_cast<float>(std::exp(-1.0 / (0.001 * ms * sampleRate_)));
  }

  float apply(int ch, float x) {
    const float rectified = std::fabs(x);
    const float c = rectified > env_[ch] ? attack_ : release_;
    env_[ch] = c * env_[ch] + (1.0f - c) * rectified;

    const float levelDb = 20.0f * std::log10(std::max(env_[ch], 1e-7f));
    const float over = levelDb - thresholdDb_;
    if (over <= 0.0f) return x * makeup_;

    const float reductionDb = over * (1.0f - 1.0f / ratio_);
    return x * static_cast<float>(dbToGain(-reductionDb)) * makeup_;
  }

  float thresholdDb_ = -18.0f, ratio_ = 4.0f, makeup_ = 1.0f;
  float attack_ = 0.0f, release_ = 0.0f;
  float env_[2] = {0.0f, 0.0f};
  double sampleRate_ = 48000.0;
};

class NoiseGate : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    env_ = 0.0f;
    gain_ = 1.0f;
  }

  void setParams(const NodeSpec& node) override {
    threshold_ = static_cast<float>(dbToGain(node.param("threshold_db", -60.0)));
    release_ = static_cast<float>(
        std::exp(-1.0 / (0.001 * node.param("release_ms", 100.0) * sampleRate_)));
  }

  void process(float* left, float* right, int n) override {
    for (int i = 0; i < n; ++i) {
      const float peak = right ? std::max(std::fabs(left[i]), std::fabs(right[i]))
                               : std::fabs(left[i]);
      env_ = std::max(peak, env_ * release_);
      const float target = env_ > threshold_ ? 1.0f : 0.0f;
      gain_ += (target - gain_) * (1.0f - release_);
      left[i] *= gain_;
      if (right) right[i] *= gain_;
    }
  }

  const char* typeName() const override { return "noise_gate"; }

 private:
  float threshold_ = 0.001f, release_ = 0.0f, env_ = 0.0f, gain_ = 1.0f;
  double sampleRate_ = 48000.0;
};

class Delay : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    // 2000 ms is the schema maximum; size once here so process() never reallocates.
    const int maxSamples = static_cast<int>(sampleRate * 2.1) + 4;
    for (auto& buf : buffers_) buf.assign(static_cast<std::size_t>(maxSamples), 0.0f);
    writeIndex_ = 0;
    damping_.setLowpass(sampleRate, 4000.0, 0.707);
  }

  void setParams(const NodeSpec& node) override {
    delaySamples_ = static_cast<int>(node.param("time_ms", 400.0) * 0.001 * sampleRate_);
    feedback_ = static_cast<float>(node.param("feedback", 0.3));
    mix_ = static_cast<float>(node.param("mix", 0.25));
    style_ = node.text("style", "digital");
    const double cutoff = style_ == "digital" ? 18000.0 : (style_ == "tape" ? 3500.0 : 5000.0);
    damping_.setLowpass(sampleRate_, cutoff, 0.707);
  }

  void process(float* left, float* right, int n) override {
    if (buffers_[0].empty() || delaySamples_ <= 0) return;
    const int size = static_cast<int>(buffers_[0].size());

    for (int i = 0; i < n; ++i) {
      const int readIndex = (writeIndex_ - delaySamples_ + size) % size;
      for (int ch = 0; ch < (right ? 2 : 1); ++ch) {
        float* channel = ch == 0 ? left : right;
        const float delayed = damping_.process(ch, buffers_[ch][readIndex]);
        buffers_[ch][writeIndex_] = channel[i] + delayed * feedback_;
        channel[i] = channel[i] * (1.0f - mix_) + delayed * mix_;
      }
      writeIndex_ = (writeIndex_ + 1) % size;
    }
  }

  const char* typeName() const override { return "delay"; }

 private:
  std::vector<float> buffers_[2];
  Biquad damping_;
  int writeIndex_ = 0, delaySamples_ = 0;
  float feedback_ = 0.3f, mix_ = 0.25f;
  std::string style_ = "digital";
  double sampleRate_ = 48000.0;
};

// Schroeder reverb: four parallel combs into two allpasses. Not a boutique algorithm, but it is
// stable, cheap, and allocation-free once prepared.
class Reverb : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    const double scale = sampleRate / 44100.0;
    static constexpr int kCombBase[kCombs] = {1557, 1617, 1491, 1422};
    static constexpr int kAllpassBase[kAllpasses] = {225, 556};

    for (int c = 0; c < kCombs; ++c) {
      for (int ch = 0; ch < 2; ++ch) {
        const int len = static_cast<int>(kCombBase[c] * scale) + (ch * 23);
        comb_[c][ch].assign(static_cast<std::size_t>(len), 0.0f);
        combIndex_[c][ch] = 0;
      }
    }
    for (int a = 0; a < kAllpasses; ++a) {
      for (int ch = 0; ch < 2; ++ch) {
        const int len = static_cast<int>(kAllpassBase[a] * scale) + (ch * 11);
        allpass_[a][ch].assign(static_cast<std::size_t>(len), 0.0f);
        allpassIndex_[a][ch] = 0;
      }
    }
  }

  void setParams(const NodeSpec& node) override {
    mix_ = static_cast<float>(node.param("mix", 0.2));
    const double decay = node.param("decay_s", 2.0);
    const double size = node.param("size", 0.5);
    feedback_ = clampf(static_cast<float>(0.7 + 0.28 * (decay / 20.0) + 0.02 * size), 0.0f, 0.98f);
  }

  void process(float* left, float* right, int n) override {
    if (comb_[0][0].empty()) return;
    for (int i = 0; i < n; ++i) {
      for (int ch = 0; ch < (right ? 2 : 1); ++ch) {
        float* channel = ch == 0 ? left : right;
        const float dry = channel[i];
        float wet = 0.0f;
        for (int c = 0; c < kCombs; ++c) wet += comb(c, ch, dry);
        wet *= 0.25f;
        for (int a = 0; a < kAllpasses; ++a) wet = allpass(a, ch, wet);
        channel[i] = dry * (1.0f - mix_) + wet * mix_;
      }
    }
  }

  const char* typeName() const override { return "reverb"; }

 private:
  static constexpr int kCombs = 4;
  static constexpr int kAllpasses = 2;

  float comb(int c, int ch, float x) {
    auto& buf = comb_[c][ch];
    int& idx = combIndex_[c][ch];
    const float y = buf[static_cast<std::size_t>(idx)];
    buf[static_cast<std::size_t>(idx)] = x + y * feedback_;
    idx = (idx + 1) % static_cast<int>(buf.size());
    return y;
  }

  float allpass(int a, int ch, float x) {
    auto& buf = allpass_[a][ch];
    int& idx = allpassIndex_[a][ch];
    const float buffered = buf[static_cast<std::size_t>(idx)];
    const float y = -x + buffered;
    buf[static_cast<std::size_t>(idx)] = x + buffered * 0.5f;
    idx = (idx + 1) % static_cast<int>(buf.size());
    return y;
  }

  std::vector<float> comb_[kCombs][2];
  std::vector<float> allpass_[kAllpasses][2];
  int combIndex_[kCombs][2] = {};
  int allpassIndex_[kAllpasses][2] = {};
  float mix_ = 0.2f, feedback_ = 0.84f;
  double sampleRate_ = 48000.0;
};

class Modulation : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    const int maxSamples = static_cast<int>(sampleRate * 0.05) + 4;
    for (auto& buf : buffers_) buf.assign(static_cast<std::size_t>(maxSamples), 0.0f);
    writeIndex_ = 0;
    phase_ = 0.0f;
  }

  void setParams(const NodeSpec& node) override {
    style_ = node.text("style", "chorus");
    rateHz_ = static_cast<float>(node.param("rate_hz", 1.0));
    depth_ = static_cast<float>(node.param("depth", 0.5));
    mix_ = static_cast<float>(node.param("mix", 0.5));
  }

  void process(float* left, float* right, int n) override {
    if (buffers_[0].empty()) return;
    const int size = static_cast<int>(buffers_[0].size());
    const float increment = rateHz_ / static_cast<float>(sampleRate_);

    for (int i = 0; i < n; ++i) {
      phase_ += increment;
      if (phase_ >= 1.0f) phase_ -= 1.0f;
      const float lfo = 0.5f * (1.0f - std::cos(6.2831853f * phase_));

      for (int ch = 0; ch < (right ? 2 : 1); ++ch) {
        float* channel = ch == 0 ? left : right;
        if (style_ == "tremolo") {
          channel[i] *= 1.0f - depth_ * lfo;
          continue;
        }
        const float baseMs = style_ == "flanger" ? 1.0f : 12.0f;
        const float sweepMs = style_ == "flanger" ? 4.0f : 6.0f;
        const int offset =
            static_cast<int>((baseMs + sweepMs * depth_ * lfo) * 0.001f * sampleRate_);
        const int readIndex = (writeIndex_ - std::min(offset, size - 1) + size) % size;
        const float delayed = buffers_[ch][static_cast<std::size_t>(readIndex)];
        buffers_[ch][static_cast<std::size_t>(writeIndex_)] = channel[i];
        channel[i] = channel[i] * (1.0f - mix_) + delayed * mix_;
      }
      writeIndex_ = (writeIndex_ + 1) % size;
    }
  }

  const char* typeName() const override { return "modulation"; }

 private:
  std::vector<float> buffers_[2];
  int writeIndex_ = 0;
  float phase_ = 0.0f, rateHz_ = 1.0f, depth_ = 0.5f, mix_ = 0.5f;
  std::string style_ = "chorus";
  double sampleRate_ = 48000.0;
};

class Filter : public Effect {
 public:
  void prepare(double sampleRate, int) override {
    sampleRate_ = sampleRate;
    filter_.reset();
  }

  void setParams(const NodeSpec& node) override {
    const std::string mode = node.text("mode", "lowpass");
    const double cutoff = node.param("cutoff_hz", 1000.0);
    // 0..1 resonance maps onto a musically useful Q range rather than a raw coefficient.
    const double q = 0.707 + node.param("resonance", 0.3) * 9.0;

    if (mode == "highpass") {
      filter_.setHighpass(sampleRate_, cutoff, q);
    } else if (mode == "bandpass" || mode == "wah") {
      // v1 has no expression input, so `wah` parks the bandpass at the requested cutoff.
      filter_.setBandpass(sampleRate_, cutoff, q);
    } else {
      filter_.setLowpass(sampleRate_, cutoff, q);
    }
  }

  void process(float* left, float* right, int n) override {
    for (int i = 0; i < n; ++i) {
      left[i] = filter_.process(0, left[i]);
      if (right) right[i] = filter_.process(1, right[i]);
    }
  }

  const char* typeName() const override { return "filter"; }

 private:
  Biquad filter_;
  double sampleRate_ = 48000.0;
};

EffectPtr makeEffect(const std::string& type);

}  // namespace tone
