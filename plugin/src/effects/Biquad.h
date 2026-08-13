#pragma once

#include <cmath>

namespace tone {

// RBJ audio-EQ cookbook biquad, transposed direct form II (one state pair per channel).
class Biquad {
 public:
  void reset() {
    for (auto& s : z1_) s = 0.0f;
    for (auto& s : z2_) s = 0.0f;
  }

  void setBell(double sampleRate, double freqHz, double q, double gainDb) {
    const double A = std::pow(10.0, gainDb / 40.0);
    const double w0 = kTwoPi * freqHz / sampleRate;
    const double alpha = std::sin(w0) / (2.0 * q);
    const double cosw = std::cos(w0);
    set(1.0 + alpha * A, -2.0 * cosw, 1.0 - alpha * A, 1.0 + alpha / A, -2.0 * cosw,
        1.0 - alpha / A);
  }

  void setLowShelf(double sampleRate, double freqHz, double q, double gainDb) {
    const double A = std::pow(10.0, gainDb / 40.0);
    const double w0 = kTwoPi * freqHz / sampleRate;
    const double cosw = std::cos(w0);
    const double alpha = std::sin(w0) / (2.0 * q);
    const double beta = 2.0 * std::sqrt(A) * alpha;
    set(A * ((A + 1) - (A - 1) * cosw + beta), 2 * A * ((A - 1) - (A + 1) * cosw),
        A * ((A + 1) - (A - 1) * cosw - beta), (A + 1) + (A - 1) * cosw + beta,
        -2 * ((A - 1) + (A + 1) * cosw), (A + 1) + (A - 1) * cosw - beta);
  }

  void setHighShelf(double sampleRate, double freqHz, double q, double gainDb) {
    const double A = std::pow(10.0, gainDb / 40.0);
    const double w0 = kTwoPi * freqHz / sampleRate;
    const double cosw = std::cos(w0);
    const double alpha = std::sin(w0) / (2.0 * q);
    const double beta = 2.0 * std::sqrt(A) * alpha;
    set(A * ((A + 1) + (A - 1) * cosw + beta), -2 * A * ((A - 1) + (A + 1) * cosw),
        A * ((A + 1) + (A - 1) * cosw - beta), (A + 1) - (A - 1) * cosw + beta,
        2 * ((A - 1) - (A + 1) * cosw), (A + 1) - (A - 1) * cosw - beta);
  }

  void setLowpass(double sampleRate, double freqHz, double q) {
    const double w0 = kTwoPi * freqHz / sampleRate;
    const double cosw = std::cos(w0);
    const double alpha = std::sin(w0) / (2.0 * q);
    const double b1 = 1.0 - cosw;
    set(b1 / 2.0, b1, b1 / 2.0, 1.0 + alpha, -2.0 * cosw, 1.0 - alpha);
  }

  void setHighpass(double sampleRate, double freqHz, double q) {
    const double w0 = kTwoPi * freqHz / sampleRate;
    const double cosw = std::cos(w0);
    const double alpha = std::sin(w0) / (2.0 * q);
    const double b1 = 1.0 + cosw;
    set(b1 / 2.0, -b1, b1 / 2.0, 1.0 + alpha, -2.0 * cosw, 1.0 - alpha);
  }

  void setBandpass(double sampleRate, double freqHz, double q) {
    const double w0 = kTwoPi * freqHz / sampleRate;
    const double cosw = std::cos(w0);
    const double alpha = std::sin(w0) / (2.0 * q);
    set(alpha, 0.0, -alpha, 1.0 + alpha, -2.0 * cosw, 1.0 - alpha);
  }

  float process(int channel, float x) {
    const float y = b0_ * x + z1_[channel];
    z1_[channel] = b1_ * x - a1_ * y + z2_[channel];
    z2_[channel] = b2_ * x - a2_ * y;
    return y;
  }

 private:
  static constexpr double kTwoPi = 6.283185307179586;

  void set(double b0, double b1, double b2, double a0, double a1, double a2) {
    b0_ = static_cast<float>(b0 / a0);
    b1_ = static_cast<float>(b1 / a0);
    b2_ = static_cast<float>(b2 / a0);
    a1_ = static_cast<float>(a1 / a0);
    a2_ = static_cast<float>(a2 / a0);
  }

  float b0_ = 1.0f, b1_ = 0.0f, b2_ = 0.0f, a1_ = 0.0f, a2_ = 0.0f;
  float z1_[2] = {0.0f, 0.0f};
  float z2_[2] = {0.0f, 0.0f};
};

}  // namespace tone
