# assets/audio

## `confirm_beep.wav`

Shared "confirmed/selected" cue — a short (200ms, 880Hz sine, mono/22050Hz/
16-bit PCM matching this project's Piper WAV format) synthesized tone, not
TTS speech. Used by the datapack-selection screen (`hardware/stm_pi_bridge/`)
when CONFIRM is pressed on a book.

Deliberately not a spoken word: language-independent, fast to recognize, and
trivially reusable by a project that doesn't have Piper available at all —
**book-scanner should reuse this exact file** for its own "확인/완료" cue
rather than creating a second one, per the project's decision to have one
unified confirmation sound across both systems. Since book-scanner isn't in
this session's scope, that reuse is left for whoever picks that work up —
this file is the canonical asset to point at.

Regenerate with `python assets/audio/generate_confirm_beep.py` if the tone
ever needs to change (parameters are in that script, not hardcoded elsewhere).
