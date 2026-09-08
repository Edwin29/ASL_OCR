# Approved-plan implementation decisions

## D-A — native audio lifecycle (before product implementation)

Current sounddevice0.5.6 on the authoritative Laptop supports RawOutputStream callback/finished_callback (runtime-context.json). Keep the controller and playback port, cache, authenticated refs, generation and priorities. Product budget2files.

Choose callback PCM supply within the existing player. One playback caller owns native construction/start/abort/close; the PortAudio callback only fills the supplied buffer from predecoded PCM and signals stop/finish. No HTTP, wave decoding, controller locks, native lifecycle calls or domain events in the callback. Input stop only sets the current cancellation Event. No dependency, backend, audio process or public port change.

Controller invalidates old epoch and signals old cancellation before publishing the replacement under its condition; stop must remain signal-only. Worker teardown must be confirmed before player.close/cache.clear. Join timeout reports failure and permits a later cleanup attempt. Callback underrun/error is a failed playback, never completion. A2 and A1 are tested as one contract. Actual native acceptance still needs bounded Windows playback tests; old AV exact root is not inferred from this correction.

Rollback: restore only approved two-file delta after stopping new owner, using baseline archive; no state migration. Tests: controllable callback lifecycle/cancel/drain/close, instant replacement, late fetch, failed shutdown; then authoritative native-only/HTTP-only/combined and H2/H3/H4. No user-interruption removal.

## D-C — revised production-fidelity evidence

Raw H1 configs have operator_preview_enabled=true, snapshot timeout12s, collection8000ms. Runtime factory wraps IP source in ThreadedPreviewCameraSource, which owns acquisition; analyzer/identity still run on application thread. The prior direct-camera CP-I1 probe is valid for preview-off composition but is not proof of H1 acquisition blocking the application. This corrects the earlier assurance's overly general description. H2/H3 recorded preview=false but those trials bypassed capture.

Do not add another camera layer or change8s/N/K. Source-local finite transient handling can use existing pull semantics: retryable read failure returns no frame, remembers bounded next-attempt time/count, and returns a terminal typed error after exhaustion. Preview worker already sleeps/polls on no-frame; it therefore survives recoverable gaps. Non-preview application does not receive an added synchronous retry loop. Response ownership, permanent401/403/TLS, frame uniqueness, same-frame identity and accepted reference remain unchanged. Engine terminal event preserves sanitized stage/status/retryability. C3 uses existing guidance policy. Direct vs preview-enabled fake tests must both run.

Full live throughput/cancel adequacy remains measurement-dependent. Existing preview stop/session and late preparation lifecycle are audited separately; do not claim local recovery solves all responsiveness or silently expand named file budget.
