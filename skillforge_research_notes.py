"""Short reference index printed without requiring an internet connection."""
REFERENCES={
 'RLGym RocketSim engine, controller order and flip flags': 'https://github.com/RLGym/rlgym/blob/main/rlgym/rocket_league/sim/rocketsim_engine.py',
 'RLGym custom state mutators': 'https://rlgym.org/Rocket%20League/Configuration%20Objects/state_mutators/',
 'RLGym tools replay-state reconstruction': 'https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/replays/convert.py',
 'Nexto non-commercial license': 'https://github.com/Rolv-Arild/Necto',
}
if __name__=='__main__':
 for name,url in REFERENCES.items():print(f'{name}: {url}')
