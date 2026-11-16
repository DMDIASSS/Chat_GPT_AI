# Continuous training and independent continuous W&B uploads

Close the stopped trainer and the old uploader console. Extract into E:\Downloads,
merging chat_gpt_ai/duelforge, then use 33_START_CONTACT_CURRICULUM.bat.

Healthy training now repeats 5M-additional-step blocks automatically until Pause,
Ctrl+C, an error/resource stop, or a failed skill gate. Checkpoints/reports remain
at block boundaries. There is no normal final 'Press any key' pause. Direct CLI
start also loops by default; --once explicitly requests a single block.

All acquisition training bypasses W&B initialization/logging even if the external
logging environment variable was not set. The separate uploader follows metrics
continuously. Stage changes keep previous run uploads alive instead of calling
finish() before opening the next run (supported W&B 0.31 create_new mode).
finish() only runs while closing the uploader, independent of training.

The submitted uploader log exposed a resume defect: SDK Run.step could report zero
while the server had already accepted step 61218305. The uploader now queries the
public API's lastHistoryStep before replaying an online run. Old rows are skipped;
new rows continue on the existing run ID. A failed history lookup retries in the
uploader and preserves metrics on disk instead of guessing and resending old rows.
No credentials, model weights, reward definitions or stage pointers are changed.

IMPORTANT: the submitted TRAJECTORY_GATE_FAILED message is a real quality pause,
not a W&B wait. This update preserves that pause and does not force an unverified
regressed policy to continue. Use 42_EVALUATE_POSSESSION_VS_PARENT.bat and existing
37_EVALUATE_CONTACT_CURRICULUM.bat, then 36_REPORT_CONTACT_CURRICULUM.bat to capture
the comparison. Healthy future blocks loop; failed-gate stops remain visible.

Regression tests cover multiple blocks, Pause, failed-gate stop, --once, server
history ahead of SDK step, and no finish() on stage transition. Tests use mocked
W&B endpoints. Existing native/learning tests are retained. Windows console launch
and actual online API access are checked on the user's machine.
