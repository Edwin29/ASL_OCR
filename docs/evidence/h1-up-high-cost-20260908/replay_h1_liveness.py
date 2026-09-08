import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, "book-scanner")

from tests.unit.video.test_engine_v3a5 import (  # noqa: E402
    FakeIdentityProvider,
    _FakePageNumberProvider,
    _artifact_id,
    _engine,
    _policy,
    _start_and_reach_ready,
)
from tests.unit.video.test_candidate import spread_frame  # noqa: E402
from book_scanner.video.events import VideoEventType  # noqa: E402
from book_scanner.video.page_number import (  # noqa: E402
    PageNumberStatus,
    SpreadPageNumberStatus,
)
from book_scanner.video.protocols import FrameSample  # noqa: E402
from book_scanner.video.types import (  # noqa: E402
    FrameId,
    ReadinessReason,
    VideoSessionState,
)


WATCH = {
    VideoEventType.OPAQUE_IDENTITY_DECIDED,
    VideoEventType.PAGE_CHANGED,
}


class TimedCamera:
    exhausted = False

    def __init__(self, rows, clock, base):
        self.rows = rows
        self.clock = clock
        self.base = base
        self.index = 0
        self.current = None

    def read(self):
        if self.index >= len(self.rows):
            return None
        if self.clock.monotonic() < self.base + self.rows[self.index]["t"]:
            return None
        self.current = self.rows[self.index]
        self.index += 1
        return FrameSample(
            FrameId("query-" + str(self.index)),
            self.clock.monotonic(),
            spread_frame(),
        )

    def stop(self):
        pass


class TimedAnalyzer:
    def __init__(self, delegate, camera, clock):
        self.delegate = delegate
        self.camera = camera
        self.clock = clock

    def analyze(self, frame):
        result = self.delegate.analyze(frame)
        row = self.camera.current
        reasons = row.get("candidate_retry_reasons", [])
        if reasons:
            self.clock.advance(row["elapsed_ms"] / 1000)
            result = replace(
                result,
                candidate=replace(
                    result.candidate,
                    retry_reasons=tuple(ReadinessReason(x) for x in reasons),
                ),
            )
        return result


class TimedProvider:
    def __init__(self, camera, clock):
        self.camera = camera
        self.clock = clock

    def observe_preview(self, *args):
        row = self.camera.current
        self.clock.advance(row["elapsed_ms"] / 1000)
        observation = _FakePageNumberProvider(
            [], preview_labels=[("11", "12")]
        ).observe_preview(*args)
        pair = row.get("pair")
        left_raw = row.get("left_raw", pair[0] if pair else None)
        right_raw = row.get("right_raw", pair[1] if pair else None)
        left_status = row.get(
            "left_status", "observed" if left_raw else "not_observed"
        )
        right_status = row.get(
            "right_status", "observed" if right_raw else "not_observed"
        )
        return replace(
            observation,
            left=replace(
                observation.left,
                raw_text=left_raw,
                normalized_label=None,
                status=PageNumberStatus(left_status),
            ),
            right=replace(
                observation.right,
                raw_text=right_raw,
                normalized_label=None,
                status=PageNumberStatus(right_status),
            ),
            key=None,
            status=SpreadPageNumberStatus.CONFLICT,
        )


def replay(name, rows, until):
    engine, clock, _, _, _, _ = _engine(
        frame_count=100,
        page_number_provider=_FakePageNumberProvider(
            [], preview_labels=[("26", "27")] * 5
        ),
        opaque_identity_policy=_policy(max_collection_ms=8000),
        provider=FakeIdentityProvider(preview_tokens=[0] * 200),
    )
    try:
        artifact_id = _artifact_id(_start_and_reach_ready(engine, clock))
        engine.delivery_confirmed(artifact_id, "receipt-reference")
        base = clock.monotonic()
        camera = TimedCamera(rows, clock, base)
        engine.camera = camera
        engine.analyzer = TimedAnalyzer(engine.analyzer, camera, clock)
        engine.page_number_provider = TimedProvider(camera, clock)
        decisions = []
        while clock.monotonic() < base + until:
            for event in engine.poll():
                if event.event_type in WATCH:
                    details = dict(event.details)
                    decisions.append(
                        {
                            "time": round(clock.monotonic() - base, 3),
                            "event": event.event_type.value,
                            "decision": details.get("decision"),
                            "n": details.get("valid_observations"),
                            "timed_out": details.get("timed_out"),
                            "coherent": details.get("coherent_numeric_difference"),
                        }
                    )
            if engine.state is VideoSessionState.SEARCHING:
                break
            clock.advance(0.02)
        result = {
            "scenario": name,
            "state": engine.state.value,
            "rows_used": camera.index,
            "decisions": decisions,
        }
        print(json.dumps(result, separators=(",", ":")))
        return result
    finally:
        engine.close()


raw = json.loads(
    Path(
        "docs/evidence/h1-camera-fresh-20260908-101447/"
        "footer-30s-native-threaded-query-01/result.json"
    ).read_text()
)["rows"]
t0 = raw[0]["observed_at_monotonic"]
native = replay(
    "native_recorded_raw_status_clean_reference",
    [dict(row, t=row["observed_at_monotonic"] - t0) for row in raw],
    33,
)
assert native["state"] == "waiting_for_page_change"
assert [d["n"] for d in native["decisions"]] == [1, 4, 2]

slow = replay(
    "stationary_exact_every_2.05_s",
    [
        {"t": 0.2 + i * 2.05, "pair": ["28", "29"], "elapsed_ms": 20}
        for i in range(20)
    ],
    38,
)
assert slow["state"] == "waiting_for_page_change"
assert [d["n"] for d in slow["decisions"]] == [4, 4, 4, 4]

unrelated = replay(
    "N5_but_unrelated_tokens",
    [
        {
            "t": 0.2 + i * 0.2,
            "pair": [str(10 + i), str(80 + i)],
            "elapsed_ms": 20,
        }
        for i in range(5)
    ],
    8.5,
)
assert unrelated["decisions"][0]["n"] == 5
assert unrelated["decisions"][0]["decision"] == "unknown"

same = replay(
    "same_page",
    [
        {"t": 0.2 + i * 1.7, "pair": ["26", "27"], "elapsed_ms": 20}
        for i in range(8)
    ],
    14,
)
assert all(
    d["decision"] == "same" and d["n"] == 1 for d in same["decisions"]
)

deadline = replay(
    "deadline_before_start_after_complete",
    [
        {
            "t": t,
            "pair": ["28", "29"],
            "elapsed_ms": 500 if i == 4 else 20,
        }
        for i, t in enumerate([0.2, 1, 2, 3, 7.9])
    ],
    9,
)
assert deadline["state"] == "searching"
assert deadline["decisions"][-1]["event"] == "page_changed"
assert deadline["decisions"][-1]["time"] > 8


def stale_visual_latch():
    labels = (
        [("30", "309")] * 5
        + [("30", "309")] * 3
        + [("38", "308")] * 5
    )
    visual = FakeIdentityProvider(preview_tokens=[0] + [1] * 3 + [0] * 5)
    engine, clock, _, preparer, _, _ = _engine(
        frame_count=30,
        page_number_provider=_FakePageNumberProvider([], preview_labels=labels),
        opaque_identity_policy=_policy(max_collection_ms=8000),
        provider=visual,
    )
    try:
        artifact_id = _artifact_id(_start_and_reach_ready(engine, clock))
        engine.delivery_confirmed(artifact_id, "receipt-a")
        rows = []
        for i in range(8):
            events = engine.poll()
            rows.append(
                {
                    "step": i + 1,
                    "state": engine.state.value,
                    "visual_latched": engine._opaque_visual_page_changed,
                    "events": [
                        {"event": event.event_type.value, **dict(event.details)}
                        for event in events
                        if event.event_type in WATCH
                        or event.event_type is VideoEventType.PAGE_CHANGE_OBSERVED
                    ],
                }
            )
            clock.advance(0.2)
        changed = [
            event
            for row in rows
            for event in row["events"]
            if event["event"] == "page_changed"
        ]
        same_at_three = [
            event
            for event in rows[2]["events"]
            if event["event"] == "opaque_identity_decided"
        ][0]
        assert same_at_three["decision"] == "same"
        assert rows[2]["visual_latched"] is True
        assert len(changed) == 1
        assert changed[0]["coherent_numeric_difference"] is False
        assert changed[0]["visual_match_kind"] is None
        assert engine.state is VideoSessionState.SEARCHING
        result = {
            "scenario": "stale_visual_latch",
            "same_at_step3": same_at_three["decision"],
            "latch_after_same_step3": rows[2]["visual_latched"],
            "steps4_to8_visual": [
                next(
                    event
                    for event in row["events"]
                    if event["event"] == "page_change_observed"
                )
                for row in rows[3:]
            ],
            "page_changed": changed[0],
            "state": engine.state.value,
            "preparations": len(preparer.calls),
            "accepted_banks": len(engine.opaque_identity_ledger.recent_accepted()),
        }
        print(json.dumps(result, separators=(",", ":")))
    finally:
        engine.close()


stale_visual_latch()
print("ASSERTIONS_PASS; no files written; production thresholds unchanged")
