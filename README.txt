Copy diagnose_actions.py and DIAGNOSE_ACTIONS.bat to your existing Chat_GPT_AI project directory next to train.py.
Double-click DIAGNOSE_ACTIONS.bat or run:
  .venv\Scripts\python.exe diagnose_actions.py --samples 3000
This compares reconstructed human controls with the PPO checkpoint on recorded human observations.
It does not start simulations, change data, or train the model.
If the latest checkpoint is not the one you want, supply --checkpoint path\to\PPO_POLICY.pt.
