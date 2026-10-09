"""Local installation sanity check."""
import platform
import sys


def main():
    print(f"Python: {sys.version.split()[0]} ({platform.system()})")
    try:
        import torch
        print(f"PyTorch: {torch.__version__} | CUDA usable: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print("GPU:", torch.cuda.get_device_name(0))
    except ImportError:
        print("PyTorch: MISSING")
    for module in ("rlgym", "rocketsim", "rlgym_ppo"):
        try:
            __import__(module)
            print(f"{module}: OK")
        except Exception as e:
            print(f"{module}: FAILED ({e})")
    try:
        from chatgpt_ai.env import build_env
        env = build_env("smoke")
        obs = env.reset()
        print("RocketSim smoke reset: OK; observation type:", type(obs).__name__)
        env.close()
    except Exception as e:
        print(f"RocketSim environment smoke reset failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
