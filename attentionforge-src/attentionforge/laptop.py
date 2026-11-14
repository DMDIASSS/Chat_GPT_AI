"""One menu for the new laptop run. Legacy attention01 stays independent."""
from pathlib import Path
from .runtime import ROOT,config

def menu(run='laptop01'):
    folder=ROOT/'runs'/run
    while True:
        print('\nATTENTIONFORGE LAPTOP — 1.09M attention, Octane 1v1\n1 Start / resume (first start benchmarks settings)\n2 Watch latest (pause training first)\n3 Evaluate vs first frozen snapshot\n4 Create report ZIP\n5 Export PT + CFG\n6 Benchmark settings only\n7 Request pause from another console\n0 Exit',flush=True)
        choice=input('Choose: ').strip()
        try:
            if choice=='0':return
            elif choice=='1':
                from .train import train
                if (folder/'config.json').exists():c=config(folder/'config.json')
                elif (ROOT/'laptop_tuned.json').exists():c=config(ROOT/'laptop_tuned.json')
                else:
                    from .tune import tune
                    c=tune()
                train(c,folder)
            elif choice=='2':
                from .cli import watch
                watch(config(),folder)
            elif choice=='3':
                from .evaluate import evaluate
                evaluate(folder,rounds=100,seconds=60)
            elif choice=='4':
                from .cli import report
                report(folder)
            elif choice=='5':
                from .cli import export
                export(folder)
            elif choice=='6':
                from .tune import tune
                tune();print('Existing runs keep their saved configuration. No training started.')
            elif choice=='7':
                if not folder.is_dir():raise FileNotFoundError('This run has not started')
                (folder/'STOP').write_text('pause requested\n');print('Pause requested; wait for PAUSED_AND_SAVED in the trainer window.')
        except KeyboardInterrupt:print('Operation interrupted. Training uses its graceful-save handler.')
        except Exception as ex:
            print(type(ex).__name__+': '+str(ex),flush=True)
            print('Operation failed. Existing runs were preserved. Keep the error text above.',flush=True)
