"""
Specify what is available to import from the taxcalc package.

The package is split into two subpackages:

- taxcalc.enginetax holds all tax-calculation code
- taxcalc.data holds the data files that code reads

The public API below is unchanged: import names directly from taxcalc
(for example, ``from taxcalc import Calculator, Policy, Records``).
"""
from taxcalc.data import DATA_PATH, DATA_PACKAGE, data_path
from taxcalc.enginetax.calculator import *
from taxcalc.enginetax.consumption import *
from taxcalc.enginetax.data import *
from taxcalc.enginetax.decorators import iterate_jit, JIT
from taxcalc.enginetax.growfactors import *
from taxcalc.enginetax.growdiff import *
from taxcalc.enginetax.parameters import *
from taxcalc.enginetax.policy import *
from taxcalc.enginetax.records import *
from taxcalc.enginetax.taxcalcio import *
from taxcalc.enginetax.utils import *
from taxcalc.cli import *

__version__ = '6.7.3'
__min_python3_version__ = 11
__max_python3_version__ = 13
