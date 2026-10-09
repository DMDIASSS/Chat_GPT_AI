"""RLBot v5 runtime. Only for offline / private matches."""
import numpy as np
from rlgym_rlbot import RLGymBot, RLGymBotConfig
from chatgpt_ai.env import make_obs, make_action_parser
from chatgpt_ai.policy import LoadedPolicy


class ChatGPTAI(RLGymBot):
    def __init__(self):
        super().__init__(
            obs_builder=make_obs(),
            action_parser=make_action_parser(),
            default_agent_id="chatgpt-ai/chat-gpt-ai/v1",
            config=RLGymBotConfig(),
        )
        self.network = LoadedPolicy()
        print(f"Chat GPT AI loaded checkpoint: {self.network.path}")

    def get_action(self, obs, game_state, packet):
        return self.network.act(np.asarray(obs, dtype=np.float32))


if __name__ == "__main__":
    ChatGPTAI().run()
