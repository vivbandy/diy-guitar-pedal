"""Pydantic v2 mirror of schema/patch.schema.json and schema/capture.manifest.schema.json.

Field names and ranges are kept identical to the JSON Schema. tests/test_schema_sync.py
asserts the two stay in agreement.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- capture manifest -------------------------------------------------------


class CaptureFormat(str, Enum):
    nam = "nam"
    wav_ir = "wav_ir"


class CaptureCategory(str, Enum):
    amp = "amp"
    pedal = "pedal"
    cab = "cab"
    outboard = "outboard"


class CaptureGain(str, Enum):
    clean = "clean"
    crunch = "crunch"
    mid_gain = "mid_gain"
    high_gain = "high_gain"
    fuzz = "fuzz"
    n_a = "n_a"


class Capture(Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    file: str
    format: CaptureFormat = CaptureFormat.nam
    category: CaptureCategory
    gain: CaptureGain = CaptureGain.n_a
    character: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    sample_rate: int | None = None
    notes: str | None = None
    includes_cab: bool = False


class CaptureManifest(Strict):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    root: str | None = None
    captures: list[Capture] = Field(default_factory=list)

    def ids(self) -> set[str]:
        return {c.id for c in self.captures}

    def by_id(self, capture_id: str) -> Capture | None:
        for c in self.captures:
            if c.id == capture_id:
                return c
        return None

    def search(self, **_: object) -> list[Capture]:
        return list(self.captures)


# --- patch nodes ------------------------------------------------------------


class NodeBase(Strict):
    enabled: bool = True
    label: str | None = None


class NamCaptureParams(Strict):
    capture_id: str
    input_level_db: float = Field(default=0, ge=-24, le=24)
    output_level_db: float = Field(default=0, ge=-24, le=24)


class NamCaptureNode(NodeBase):
    type: Literal["nam_capture"]
    params: NamCaptureParams


class IrCabParams(Strict):
    capture_id: str
    level_db: float = Field(default=0, ge=-24, le=24)


class IrCabNode(NodeBase):
    type: Literal["ir_cab"]
    params: IrCabParams


class DriveStyle(str, Enum):
    boost = "boost"
    overdrive = "overdrive"
    distortion = "distortion"
    fuzz = "fuzz"


class DriveParams(Strict):
    style: DriveStyle = DriveStyle.overdrive
    drive: float = Field(default=0.5, ge=0, le=1)
    tone: float = Field(default=0.5, ge=0, le=1)
    level: float = Field(default=0.5, ge=0, le=1)


class DriveNode(NodeBase):
    type: Literal["drive"]
    params: DriveParams = Field(default_factory=DriveParams)


class CompressorParams(Strict):
    threshold_db: float = Field(default=-18, ge=-60, le=0)
    ratio: float = Field(default=4, ge=1, le=20)
    attack_ms: float = Field(default=10, ge=0.1, le=200)
    release_ms: float = Field(default=100, ge=1, le=1000)
    makeup_db: float = Field(default=0, ge=0, le=24)


class CompressorNode(NodeBase):
    type: Literal["compressor"]
    params: CompressorParams = Field(default_factory=CompressorParams)


class NoiseGateParams(Strict):
    threshold_db: float = Field(default=-60, ge=-90, le=0)
    release_ms: float = Field(default=100, ge=1, le=1000)


class NoiseGateNode(NodeBase):
    type: Literal["noise_gate"]
    params: NoiseGateParams = Field(default_factory=NoiseGateParams)


class EqShape(str, Enum):
    bell = "bell"
    low_shelf = "low_shelf"
    high_shelf = "high_shelf"


class EqBand(Strict):
    freq_hz: float = Field(ge=20, le=20000)
    gain_db: float = Field(ge=-18, le=18)
    q: float = Field(default=0.7, ge=0.1, le=10)
    shape: EqShape = EqShape.bell


class EqParams(Strict):
    bands: list[EqBand] = Field(default_factory=list, max_length=8)


class EqNode(NodeBase):
    type: Literal["eq"]
    params: EqParams = Field(default_factory=EqParams)


class DelayStyle(str, Enum):
    digital = "digital"
    analog = "analog"
    tape = "tape"


class DelayParams(Strict):
    time_ms: float = Field(default=400, ge=0, le=2000)
    feedback: float = Field(default=0.3, ge=0, le=0.95)
    mix: float = Field(default=0.25, ge=0, le=1)
    style: DelayStyle = DelayStyle.digital


class DelayNode(NodeBase):
    type: Literal["delay"]
    params: DelayParams = Field(default_factory=DelayParams)


class ReverbStyle(str, Enum):
    room = "room"
    hall = "hall"
    plate = "plate"
    spring = "spring"


class ReverbParams(Strict):
    size: float = Field(default=0.5, ge=0, le=1)
    decay_s: float = Field(default=2, ge=0.1, le=20)
    mix: float = Field(default=0.2, ge=0, le=1)
    style: ReverbStyle = ReverbStyle.hall


class ReverbNode(NodeBase):
    type: Literal["reverb"]
    params: ReverbParams = Field(default_factory=ReverbParams)


class ModulationStyle(str, Enum):
    chorus = "chorus"
    flanger = "flanger"
    phaser = "phaser"
    tremolo = "tremolo"


class ModulationParams(Strict):
    style: ModulationStyle = ModulationStyle.chorus
    rate_hz: float = Field(default=1, ge=0.01, le=20)
    depth: float = Field(default=0.5, ge=0, le=1)
    mix: float = Field(default=0.5, ge=0, le=1)


class ModulationNode(NodeBase):
    type: Literal["modulation"]
    params: ModulationParams = Field(default_factory=ModulationParams)


class FilterMode(str, Enum):
    lowpass = "lowpass"
    highpass = "highpass"
    bandpass = "bandpass"
    wah = "wah"


class FilterParams(Strict):
    mode: FilterMode = FilterMode.lowpass
    cutoff_hz: float = Field(default=1000, ge=20, le=20000)
    resonance: float = Field(default=0.3, ge=0, le=1)


class FilterNode(NodeBase):
    type: Literal["filter"]
    params: FilterParams = Field(default_factory=FilterParams)


Node = Annotated[
    NamCaptureNode
    | IrCabNode
    | DriveNode
    | CompressorNode
    | NoiseGateNode
    | EqNode
    | DelayNode
    | ReverbNode
    | ModulationNode
    | FilterNode,
    Field(discriminator="type"),
]

CAPTURE_NODE_TYPES = ("nam_capture", "ir_cab")


# --- patch ------------------------------------------------------------------


class Reference(Strict):
    artist: str | None = None
    song: str | None = None
    notes: str | None = None


class Io(Strict):
    input_gain_db: float = Field(default=0, ge=-24, le=24)
    output_gain_db: float = Field(default=0, ge=-24, le=24)


class Patch(Strict):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    source_request: str | None = None
    reference: Reference | None = None
    created_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    io: Io = Field(default_factory=Io)
    chain: list[Node] = Field(min_length=1)

    def capture_ids(self) -> list[str]:
        return [n.params.capture_id for n in self.chain if n.type in CAPTURE_NODE_TYPES]
