"""SourceFileLoader.load_module() is gone in Python 3.15; load an extensionless bin/ script as a module."""
import importlib.machinery, importlib.util, sys


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    sys.modules[name] = module
    loader.exec_module(module)
    return module
