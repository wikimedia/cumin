"""Automation and orchestration framework written in Python."""
from pkg_resources import DistributionNotFound, get_distribution


try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    pass  # package is not installed


class CuminError(Exception):
    """Base Exception class for all Cumin's custom Exceptions."""
