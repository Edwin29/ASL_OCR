from book_scanner.video.opaque_identity import OpaqueFooterTokenPair
from book_scanner.video.types import FrameId

pair = OpaqueFooterTokenPair(
    "26",
    "27",
    FrameId("diagnostic-smoke"),
    1.0,
    "diagnostic",
    "diagnostic:1",
    "0" * 64,
    "1" * 64,
)
assert list(pair.value) == ["26", "27"]
print("opaque_pair_contract_smoke=PASS")
