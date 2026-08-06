#!/usr/bin/env python3
"""Top-level entrypoint wrapper for the Language Accessibility Checker.

This thin wrapper exists so the package can use proper relative imports
(``from .detector import ...``) while still being runnable directly from
the project root without installing the package into site-packages.

Usage:
    python main.py --sitemap ./sitemap.xml

The real implementation lives in ``src/main.py``.
"""

import sys
from pathlib import Path

# Ensure the project root is on the path so ``import src`` resolves
# correctly when running this wrapper directly.
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
