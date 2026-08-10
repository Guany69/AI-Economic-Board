"""
Data assets shipped with the taxcalc package.

This subpackage holds every non-code input the engine reads: the input
sample files, the weights files, the growth-factor file, and the JSON
files that define policy parameters and variable metadata.  No tax logic
lives here.

Engine modules must locate these files through DATA_PATH or data_path()
rather than deriving a path from their own __file__, so that the split
between engine code and data stays a single-point-of-change.

Note: do not confuse this subpackage (taxcalc.data) with the module
taxcalc.enginetax.data, which defines the abstract Data class.
"""
import os

# absolute path to the directory holding the data assets
DATA_PATH = os.path.abspath(os.path.dirname(__file__))

# name of this subpackage, for importlib.resources lookups when taxcalc
# is installed as a zipped package rather than as plain files on disk
DATA_PACKAGE = 'taxcalc.data'

# data files that are part of the package (as opposed to files a user
# supplies at run time, such as puf.csv and its weights and ratios)
PACKAGE_DATA_FILES = [
    'consumption.json',
    'cps.csv.gz',
    'cps_weights.csv.gz',
    'growdiff.json',
    'growfactors.csv',
    'policy_current_law.json',
    'records_variables.json',
]


def data_path(filename):
    """
    Return absolute path to the specified data file in this subpackage.
    """
    return os.path.join(DATA_PATH, filename)
