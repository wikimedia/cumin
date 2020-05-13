"""Colors module."""
from abc import ABCMeta


class ColoredType(ABCMeta):
    """Metaclass to define a new type that dynamically adds static methods to its classes."""

    COLORS = {
        'red': 31,
        'green': 32,
        'yellow': 33,
        'blue': 34,
        'cyan': 36,
    }
    """:py:class:`dict`: a mapping of colors to the ANSI foreground color code."""

    def __getattr__(cls, name):  # noqa: N805 (Prospector reqires an older version of pep8-naming)
        """Dynamically check access to members of classes of this type.

        :Parameters:
            according to Python's Data model :py:meth:`object.__getattr__`.

        """
        color_code = ColoredType.COLORS.get(name, None)
        if color_code is None:
            raise AttributeError("'{cls}' object has no attribute '{attr}'".format(cls=cls.__name__, attr=name))

        return lambda obj: cls._color(color_code, obj)


class Colored(metaclass=ColoredType):
    """Class to manage colored output.

    Available methods are dynamically added based on the keys of the :py:const:`ColoredType.COLORS` dictionary.
    For each color a method with the color name is available to color any object with that specific color code.

    Examples::

        Colored.green(object)

    """

    disabled = False
    """:py:class:`bool`: switch to globally control the coloring. Set it to :py:const`True` to disable all coloring."""

    @staticmethod
    def _color(color_code, obj):
        """Color the given object, unless coloring is globally disabled.

        Arguments:
            color_code (int): a valid ANSI escape sequence color code.
            obj (mixed): the object to color.

        Return:
            str: the string representation of the object encapsulated in the red ANSI escape sequence.

        """
        message = str(obj)

        if not message:
            return ''

        if Colored.disabled:
            return message

        return '\x1b[{code}m{message}\x1b[39m'.format(code=color_code, message=message)
