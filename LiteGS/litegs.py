import importlib
import sys

_pkg = importlib.import_module("LiteGS")
sys.modules[__name__] = _pkg
