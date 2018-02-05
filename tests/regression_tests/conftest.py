import openmc
import pytest


@pytest.fixture(scope='module', autouse=True)
def setup_regression_test(request):
    # Reset autogenerated IDs assigned to OpenMC objects
    openmc.reset_auto_ids()

    # Change to test directory
    olddir = request.fspath.dirpath().chdir()
    try:
        yield
    finally:
        olddir.chdir()
