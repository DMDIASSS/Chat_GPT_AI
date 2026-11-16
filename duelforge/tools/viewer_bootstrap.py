"""Set camera defaults in the viewer process; do not edit an existing viewer install."""
import sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'src'))
import config
original=config.Config.__init__
def defaults(self):
    original(self)
    self.camera_distance.val=270;self.camera_height.val=100;self.camera_fov.val=110
config.Config.__init__=defaults
import main
main.main()
