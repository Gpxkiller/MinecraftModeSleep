"""Build a worker source ZIP from an explicit allowlist, excluding caches/configs."""
from pathlib import Path
import hashlib, zipfile

def package(root, destination):
 root=Path(root).resolve();destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 selected=['daemon/modesleep.py','daemon/config.example.json','deploy/minecraft-mode-sleep.service','deploy/minecraft-mode-sleep.timer','README.md','SECURITY.md','VALIDATION.md','CHANGELOG.md','LICENSE']
 target=destination/'MinecraftModeSleep-worker.zip'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
  for name in selected:
   path=root/name
   if path.is_symlink():raise ValueError('Linked source refused')
   archive.write(path,name)
 return target

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
 target=package(Path(__file__).parents[1],args.output)
 print(target.name+' sha256:'+hashlib.sha256(target.read_bytes()).hexdigest())
