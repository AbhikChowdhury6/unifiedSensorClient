import os
import sys

# Ensure project root is on sys.path for absolute imports like `writers.*` and `config`
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

