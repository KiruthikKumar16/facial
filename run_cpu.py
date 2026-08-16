#!/usr/bin/env python
"""Entry point for running facial recognition surveillance system on CPU."""

import sys
from pathlib import Path

# Add facial_recognition module to path
sys.path.insert(0, str(Path(__file__).parent))

from facial_recognition.main_cpu import main

if __name__ == '__main__':
    main()
