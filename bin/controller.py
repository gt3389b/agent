#!/usr/bin/env python3
"""USP Controller launcher"""

import sys
import os
import runpy

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == '__main__':
    runpy.run_module("controller.main", run_name="__main__")
