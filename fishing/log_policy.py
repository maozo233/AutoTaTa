"""Compatibility alias for the common log service."""
import sys
from autotata import log_policy as _shared
sys.modules[__name__] = _shared
