"""Publication guard for source/example files, no production data required."""
from pathlib import Path
import re, unittest

class PublicationTests(unittest.TestCase):
 def test_only_generic_source_and_examples(self):
  root=Path(__file__).parents[1]
  forbidden=re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|C:[/\\]Users[/\\]',re.I)
  checked=0
  for path in root.rglob('*'):
   if not path.is_file() or any(p in {'.git','target','dist','__pycache__'} for p in path.relative_to(root).parts):continue
   self.assertNotIn(path.suffix.lower(),{'.sqlite','.mca','.dat','.log','.png','.jpg'},str(path.relative_to(root)))
   text=path.read_text(encoding='utf8');self.assertIsNone(forbidden.search(text),str(path.relative_to(root)))
   for ip in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',text):
    self.assertEqual(ip,'127.0.0.1',str(path.relative_to(root)))
   checked+=1
  self.assertGreaterEqual(checked,15)

if __name__=='__main__':unittest.main()
