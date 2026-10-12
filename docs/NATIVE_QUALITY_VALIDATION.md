# Native quality validation

Validated in the cloud with GCC 14, CPU PyTorch 2.14.1 and the pinned public
GigaLearn source. Windows/MSVC/CUDA execution of this update requires the local
rebuild described in the campaign guide.

- 47 tests passed across native quality, native setup, Replicar integration and
  versatile trainer suites.
- Fresh and previous-patch Windows CRLF source fixtures upgraded successfully;
  repeated installation worked and unknown user edits were preserved.
- The C++ executable was rebuilt with the evaluation probe and campaign hooks.
- 96 generated parity cases covered both colors, 1v1/2v2/3v3, rotations, boost
  timers, exhausted flips, zero boost, turtle contact, demos and previous
  controls. Masks and chosen actions matched. Maximum observation error was
  1.20e-7; maximum probability error was 1.87e-8.
- A four-iteration native test actually collected from eight learner players
  and eight frozen players per iteration. It recorded 2,184 scripted kickoff
  physics ticks and 20 practice resets. Original checkpoint files were kept.
- A reduced-budget CPU campaign completed replay BC, mixed/focused branches,
  independent match selection and the untouched replay report. Inconclusive
  matches retained Nexto rather than reporting an unsupported improvement.
- Separate same-model retention checks exercised all nine skill tasks and
  2v2/3v3 evaluation.

These tests establish integration and conservative selection behavior, not the
strength of the user's locally trained models. Generated fixtures are not SSL
replay evidence. The C++/Python inference parity check does not establish
simulator physics parity or native RLBot/browser deployment.

## Overnight loop

The combined suites pass 56 tests, including nine overnight-specific checks
for tied-ranking persistence, interrupted/frozen confirmations, retention
failures, resumable evaluation, completed chunk reuse and disk preservation.
A reduced-budget real C++ run completed BC, mixed/focused training, individual
checkpoint screens, mechanics assessment and fresh confirmation. A second
cycle was paused during screening and resumed to completion; all previously
screened native/Nexto file identities remained unchanged. These fixtures use
short test budgets and do not establish the user's local model strength.
