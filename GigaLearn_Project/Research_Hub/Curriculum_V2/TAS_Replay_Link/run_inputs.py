"""Auto-discover the current extracted replay dataset and run input-following comparisons."""
import json
from run_pipeline import find_replays,ROOT,HERE
from train_controls_v2 import train
if __name__=='__main__':
    dataset=find_replays()
    print('Using existing replay analysis:',dataset,flush=True)
    print(json.dumps(train(ROOT/'data/tas',dataset,HERE/'results',epochs=4,stride=3),indent=2))
