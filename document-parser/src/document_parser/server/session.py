"""`DatapackSession`: one active navigation session over one loaded
`Datapack`. Reuses `SpeechController`/`BraillePresenter` completely
unchanged -- the whole point of a serving-ready datapack (see
docs/datapack-schema.md) is that navigation state transitions and braille
rendering are cheap pure Python and can run live, while OCR and TTS
synthesis (the two real model-inference costs) never happen here.
"""

from __future__ import annotations

from typing import Any, Callable

from document_parser.accessibility import BraillePresenter, NavigationCommand, NavigationState, SpeechController
from document_parser.accessibility.application.speech_controller import BrailleRenderFailure
from document_parser.accessibility.speech import normalize_tts_pronunciation
from document_parser.datapack.loader import Datapack


class DatapackTtsEngineAdapter:
    """`TtsEngineAdapter` that looks up pre-synthesized audio by exact
    utterance text instead of calling a real TTS engine -- see
    `Datapack.audio_by_text`.

    Exact lookup remains the primary path.  For an older immutable revision,
    a TTS-only pronunciation update can change the current lookup text while
    its existing WAV still contains the same semantic utterance.  A secondary
    index under today's pronunciation normalization keeps that revision
    readable until maintenance re-synthesizes it.  Unrelated misses still
    raise loudly; the compatibility path never guesses by item order.

    `on_complete` fires immediately, like `ConsoleTtsEngineAdapter` -- real
    playback happens on remote hardware whose completion ACK doesn't exist
    yet (Phase 5 hardware transport, still unbuilt). Continuous reading
    (DOWN LONG) will auto-advance instantly rather than waiting for real
    audio duration until that exists; revisit then.
    """

    def __init__(self, audio_by_text: dict[str, dict[str, Any]]) -> None:
        self._audio_by_text = audio_by_text
        self._audio_by_normalized_text: dict[str, dict[str, Any]] = {}
        for stored_text, entry in audio_by_text.items():
            normalized = normalize_tts_pronunciation(stored_text)
            self._audio_by_normalized_text.setdefault(normalized, entry)
        self._on_complete: Callable[[int], None] | None = None
        self.spoken: list[tuple[str, int]] = []
        self.last_audio: dict[str, Any] | None = None
        self.last_audio_generation: int | None = None

    def on_complete(self, callback: Callable[[int], None]) -> None:
        self._on_complete = callback

    def speak(self, text: str, generation: int) -> None:
        self.spoken.append((text, generation))
        entry = self._audio_by_text.get(text)
        if entry is None:
            entry = self._audio_by_normalized_text.get(text)
        if entry is None:
            raise KeyError(
                f"No pre-synthesized audio for utterance {text!r}. The datapack's ingest run "
                "and the live navigator have drifted apart -- re-ingest this book."
            )
        self.last_audio = entry
        self.last_audio_generation = generation
        if self._on_complete is not None:
            self._on_complete(generation)

    def cancel(self) -> None:
        pass


class DatapackSession:
    """Transport-agnostic session core: wraps one `SpeechController` driving
    one `Datapack`. A future HTTP/WebSocket/serial layer calls
    `handle_button` per button event and sends `braille_frame`/`audio` on to
    the hardware -- nothing in this class knows or cares how it got called.
    """

    def __init__(
        self,
        datapack: Datapack,
        initial_state: NavigationState | None = None,
        braille_presenter: BraillePresenter | None = None,
    ) -> None:
        self.datapack = datapack
        state = initial_state or NavigationState(document_id=datapack.document["document_id"], page_index=0, node_index=0)
        self._engine = DatapackTtsEngineAdapter(datapack.audio_by_text)
        self._controller = SpeechController(
            datapack.document, state, self._engine, braille_presenter or BraillePresenter()
        )
        self._controller.speak_current()

    @property
    def state(self) -> NavigationState:
        return self._controller.state

    @property
    def braille_frame(self) -> dict[str, Any]:
        return self._controller.braille_frame

    @property
    def braille_failures(self) -> tuple[BrailleRenderFailure, ...]:
        return self._controller.braille_failures

    @property
    def audio(self) -> dict[str, Any] | None:
        """Audio to play for the *current* state, or `None` if this turn was
        a silent braille-only scroll (Decision 2: pure within-span/
        within-cell window movement never re-announces). Compares against
        `state.generation` rather than just returning the engine's last
        spoken entry -- otherwise a transport would incorrectly replay
        stale audio from a few turns ago on every silent scroll, since
        `speak()` simply isn't called on those turns."""
        if self._engine.last_audio_generation != self.state.generation:
            return None
        return self._engine.last_audio

    def handle_button(self, command: NavigationCommand) -> dict[str, Any]:
        self._controller.handle_command(command)
        return {"state": self.state, "braille_frame": self.braille_frame, "audio": self.audio}
