"""pytest conftest — adds v2 root to sys.path so all imports resolve."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
