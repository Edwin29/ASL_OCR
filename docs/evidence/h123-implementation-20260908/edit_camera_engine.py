from pathlib import Path
p=Path(__file__).resolve().parents[3]/'book-scanner/src/book_scanner/video/engine.py'
s=p.read_text(encoding='utf-8')
s=s.replace('from .sources import CameraUnavailableError, FrameDecodeError, SystemClock','from .sources import CameraUnavailableError, FrameDecodeError, SnapshotTransportError, SystemClock')
# Match only camera read handlers, preserving existing decode taxonomy.
for indent, returned in [(12,'tuple(events)'),(8,'None'),(8,'None')]:
    # The two 8-space handlers return None and bare return respectively below.
    pass
s=s.replace('            except FrameDecodeError:\n', '''            except SnapshotTransportError as exc:
                self._fail_snapshot(exc, events)
                return tuple(events)
            except FrameDecodeError:
''',1)
start=s.index('    def _read_frame_for_opaque')
at=s.index('        except FrameDecodeError:',start)
s=s[:at]+'''        except SnapshotTransportError as exc:
            self._fail_snapshot(exc, events)
            return None
'''+s[at:]
start=s.index('    def _poll_page_change(')
at=s.index('        except FrameDecodeError:',start)
s=s[:at]+'''        except SnapshotTransportError as exc:
            self._fail_snapshot(exc, events)
            return
'''+s[at:]
s=s.replace('        self._opaque_identity_unknown_timeouts = 0','        self._opaque_identity_unknown_timeouts = 0\n        self._page_change_guidance_pending = False',1)
s=s.replace('            self.guidance.reset()','            self.guidance.reset()\n            self._page_change_guidance_pending = False',1)
start=s.index('    def _poll_opaque_page_change(')
end=s.index('    def _read_frame_for_opaque',start)
part=s[start:end]
part=part.replace('        if timeout.timed_out:\n','        if timeout.timed_out:\n            self._page_change_guidance_pending = True\n',1)
part=part.replace('        if frame is None:\n            return','''        if frame is None:
            if self._page_change_guidance_pending:
                self._page_change_guidance(ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE, events)
            return''',1)
part=part.replace('        if analyzed.candidate.retry_reasons:\n','''        if analyzed.candidate.retry_reasons:
            self._page_change_guidance(analyzed.candidate.retry_reasons[0], events)
''',1)
part=part.replace('        if decision.kind is OpaqueIdentityDecisionKind.UNKNOWN:\n            return','''        if decision.kind is OpaqueIdentityDecisionKind.UNKNOWN:
            if pair is None or self._page_change_guidance_pending:
                self._page_change_guidance(ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE, events)
            return''',1)
part=part.replace('        if decision.kind is OpaqueIdentityDecisionKind.SAME:\n','''        if decision.kind is OpaqueIdentityDecisionKind.SAME:
            self.guidance.observe(None, self.clock.monotonic())
            self._page_change_guidance_pending = False
''',1)
part=part.replace('        self.guidance.reset()','        self.guidance.reset()\n        self._page_change_guidance_pending = False',1)
s=s[:start]+part+s[end:]
at=s.index('    def _read_frame_for_opaque')
s=s[:at]+'''    def _page_change_guidance(self, reason: ReadinessReason, events: list[VideoEvent]) -> None:
        if self.state is not VideoSessionState.WAITING_FOR_PAGE_CHANGE:
            return
        guidance = self.guidance.observe(reason, self.clock.monotonic())
        if guidance is not None:
            events.append(self._event(
                VideoEventType.GUIDANCE_REQUESTED, reason=guidance.reason,
                details={"identity_role": OpaqueIdentityRole.PAGE_CHANGE.value,
                         "stable_for_samples": guidance.stable_for_samples,
                         "stable_for_ms": guidance.stable_for_ms},
            ))

'''+s[at:]
at=s.index('    def _fail(self,')
s=s[:at]+'''    def _fail_snapshot(self, error: SnapshotTransportError, events: list[VideoEvent]) -> None:
        self._fail(ReadinessReason.CAMERA_UNAVAILABLE, events, details={
            "stage": "http_snapshot", "error_class": type(error).__name__,
            "retryable": error.retryable, "http_status": error.status_code,
        })

'''+s[at:]
s=s.replace('    def _fail(self, reason: ReadinessReason, events: list[VideoEvent]) -> None:', '    def _fail(self, reason: ReadinessReason, events: list[VideoEvent], *, details=None) -> None:',1)
s=s.replace('events.append(self._event(VideoEventType.SESSION_ERROR, reason=reason))','events.append(self._event(VideoEventType.SESSION_ERROR, reason=reason, details=details or {}))',1)
p.write_text(s,encoding='utf-8')
