import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure backend root is ahead of tests directory in sys.path to prevent namespace collisions
while TESTS_DIR in sys.path:
    sys.path.remove(TESTS_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
