"""Civora AI — one command for the whole regression suite (v2.4).

    cd /d C:\\Civora_AI
    .venv\\Scripts\\python.exe run_tests.py

Runs every test_*.py in this folder. The full-app smoke test works on a temporary
copy of the source, so the real database (data\\buildquant.db) is never modified.
Exit code 0 = all passed.
"""
import os, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

# Make Tesseract visible for OCR tests on a default Windows install.
for folder in (r'C:\Program Files\Tesseract-OCR', r'C:\Program Files (x86)\Tesseract-OCR'):
    if os.path.isfile(os.path.join(folder, 'tesseract.exe')) and folder not in os.environ.get('PATH', ''):
        os.environ['PATH'] = folder + os.pathsep + os.environ.get('PATH', '')

def main():
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_*.py', top_level_dir=str(HERE))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    skipped = len(result.skipped)
    print('\n' + '=' * 60)
    print(f'CIVORA TESTS: {result.testsRun} run, {len(result.failures)} failed, '
          f'{len(result.errors)} errors, {skipped} skipped')
    for test, reason in result.skipped:
        print(f'  SKIPPED {test.id()}: {reason}')
    ok = result.wasSuccessful()
    print('RESULT: PASS' if ok else 'RESULT: FAIL — do not use this build; see errors above')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
