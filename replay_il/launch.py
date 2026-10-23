"""Console and UTF-8 logfile stay available when launched from a BAT file."""
from pathlib import Path
import sys,traceback

class Tee:
    def __init__(self,screen,log):self.screen=screen;self.log=log
    def write(self,text):self.screen.write(text);self.log.write(text);self.flush()
    def flush(self):self.screen.flush();self.log.flush()
    def isatty(self):return self.screen.isatty()
    @property
    def encoding(self):return self.screen.encoding
    def __getattr__(self,name):return getattr(self.screen,name)

def main():
    root=Path(__file__).resolve().parents[1];path=root/'data/isolated/replay_imitation/launcher.log';path.parent.mkdir(parents=True,exist_ok=True)
    print('Replay imitation launcher. Log:',path,flush=True)
    stdout,stderr=sys.stdout,sys.stderr
    with path.open('a',encoding='utf8') as log:
        sys.stdout=Tee(stdout,log);sys.stderr=Tee(stderr,log)
        try:
            from replay_il.__main__ import main as run
            run(sys.argv[1:])
        except Exception:
            traceback.print_exc();return 1
        finally:sys.stdout,sys.stderr=stdout,stderr
    return 0

if __name__=='__main__':sys.exit(main())
