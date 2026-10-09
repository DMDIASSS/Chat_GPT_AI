"""Cross-entropy action timing search in RocketSim; records only verified runs.

The optimizer is CEM (derivative-free reinforcement learning). It does not
change a single Nexto weight. Search fitness is diagnostic, success requires
strict verifier gates. Successful physical demonstrations are saved for BC.
"""
import argparse, json, os, tempfile
from pathlib import Path
import numpy as np
from skillforge_core import Simulator, rollout, search_parameters, output_metrics

ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT/'data'/'skillforge'/'wavedash'


def parse():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=DEFAULT_DIR)
    p.add_argument('--population',type=int,default=30)
    p.add_argument('--generations',type=int,default=8)
    p.add_argument('--training-seeds',type=int,default=4)
    p.add_argument('--holdout-seeds',type=int,default=16)
    p.add_argument('--seed',type=int,default=1001)
    p.add_argument('--variant',choices=('forward','side','airroll_only'),default='forward')
    p.add_argument('--difficulty',choices=('near','varied'),default='near')
    p.add_argument('--max-ticks',type=int,default=100)
    p.add_argument('--minimum-holdout-success',type=float,default=0.5)
    return p


def safe_save_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    name=path.with_name(path.name+'.partial')
    name.write_text(json.dumps(value,indent=2),encoding='utf-8')
    os.replace(name,path)


def search(args):
    if min(args.population,args.generations,args.training_seeds,args.holdout_seeds,args.max_ticks)<1:
        raise ValueError('All counts must be positive')
    if not 0 <= args.minimum_holdout_success <= 1:
        raise ValueError('Holdout threshold must be in [0,1]')
    args.out.mkdir(parents=True,exist_ok=True)
    # Never touch an existing validated artifact unless user selects a new output path.
    final=args.out/'discovery.json'
    demos=args.out/'verified_demonstrations.json'
    if final.exists() or demos.exists():
        raise FileExistsError(f'Existing discovery at {final}; choose --out new_directory')
    rng=np.random.default_rng(args.seed)
    # Independent RNG for training vs holdout: no holdout-driven CEM selection.
    train_seeds=list(range(args.seed*100+1,args.seed*100+args.training_seeds+1))
    holdout_seeds=list(range(args.seed*100+100001,args.seed*100+100001+args.holdout_seeds))
    history=[]
    mean=None; std=None; best=None; best_score=-1e12
    sim=Simulator()
    try:
        for gen in range(args.generations):
            entries=[]
            for i in range(args.population):
                p=search_parameters(rng,mean,std)
                if gen==0 and i==0:
                    # A simple hand-coded seed, still MUST pass physical verifier.
                    p.update({'delay':7,'hold':1,'cancel_delay':1,'cancel_ticks':12,'pre':0.,'post':0.})
                scores=[]; successes=[]
                for seed in train_seeds:
                    metrics,_=rollout(sim,seed,p,variant=args.variant,
                        difficulty=args.difficulty,max_ticks=args.max_ticks)
                    scores.append(metrics.fitness)
                    successes.append(bool(metrics.success))
                # Optimize average quality with slight worst-case pressure.
                score=float(np.mean(scores)+0.20*min(scores))
                entries.append((score,p,int(sum(successes))))
                if score>best_score:
                    best_score=score; best=dict(p)
            entries.sort(key=lambda t:t[0],reverse=True)
            elite=entries[:max(3,int(round(args.population*0.25)))]
            keys=('delay','hold','cancel_delay','cancel_ticks','pre','post')
            mean={k:float(np.mean([x[1][k] for x in elite])) for k in keys}
            std={k:max(0.3 if k not in ('pre','post') else 0.07,
                       float(np.std([x[1][k] for x in elite]))) for k in keys}
            row={'generation':gen+1,'highest_score':round(entries[0][0],3),
                 'best_successes_on_train':entries[0][2],
                 'average_successes_on_train':round(np.mean([x[2] for x in entries]),2),
                 'candidate':entries[0][1]}
            history.append(row)
            print(f'Gen {gen+1}/{args.generations} | best fitness {row["highest_score"]:.3f}'
                  f' | physical success {row["best_successes_on_train"]}/{args.training_seeds}'
                  f' | sample pass avg {row["average_successes_on_train"]}',flush=True)
            safe_save_json(args.out/'search_progress.json',
                           {'completed_generations':len(history),'history':history})
        holdouts=[]
        examples=[]
        # Only collect demonstrations from TRAINING seeds. Never train on holdout.
        for seed in train_seeds:
            metrics,trajectory=rollout(sim,seed,best,variant=args.variant,
                       difficulty=args.difficulty,max_ticks=args.max_ticks,frames=True)
            if metrics.success:
                examples.append({'seed':seed,'trajectory':trajectory,'metric':output_metrics(metrics)})
        for seed in holdout_seeds:
            metrics,_=rollout(sim,seed,best,variant=args.variant,
                       difficulty=args.difficulty,max_ticks=args.max_ticks)
            holdouts.append({'seed':seed,**output_metrics(metrics)})
        passed=sum(int(x['success']) for x in holdouts)
        result={'type':'skillforge-wavedash-discovery-v1',
            'variant':args.variant,'difficulty':args.difficulty,
            'candidate':best,'best_training_fitness':best_score,
            'training_seeds':train_seeds,'holdout_seeds':holdout_seeds,
            'holdout_wins':passed,'holdout_total':len(holdouts),
            'holdout_fraction':passed/len(holdouts),'required_holdout_fraction':args.minimum_holdout_success,
            'eligible_for_imitation':passed/len(holdouts)>=args.minimum_holdout_success,
            'holdout_results':holdouts,'history':history}
        safe_save_json(final,result)
        if examples:
            safe_save_json(demos,{'format':'skillforge-tick-control-v1',
                 'variant':args.variant,'examples':examples})
        print(f'Holdout: {passed}/{len(holdouts)} physically verified wavedashes',flush=True)
        if result['eligible_for_imitation']:
            print('Candidate passed holdout threshold. Demonstrations saved; optional BC can run.',flush=True)
        else:
            print('NOT PROMOTED. Low holdout success; adjust scenarios/search. No learned bot produced.',flush=True)
        print(f'Report: {final}',flush=True)
        return result
    finally:
        sim.close()


if __name__=='__main__': search(parse().parse_args())
