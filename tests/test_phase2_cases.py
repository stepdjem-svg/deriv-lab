import inspect
import unittest
from tests import test_phase2 as m


class Phase2Tests(unittest.TestCase):
    pass


def _make(fn):
    def runner(self):
        fn()
    return runner


for _name, _fn in sorted(vars(m).items()):
    if _name.startswith("test_") and inspect.isfunction(_fn):
        if inspect.signature(_fn).parameters:
            setattr(Phase2Tests, _name, unittest.skip("needs fixtures")(_make(_fn)))
        else:
            setattr(Phase2Tests, _name, _make(_fn))

if __name__ == "__main__":
    unittest.main()
