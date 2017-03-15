"""
Functions to extend the event system.

These funcitons are not helpers (helpers are in a separate module)
and are designed to be used more by developers to add event types.

"""

from textwrap import dedent

from django.conf import settings
from evennia import logger
from evennia import ScriptDB
from evennia.contrib.custom_gametime import UNITS
from evennia.contrib.custom_gametime import real_seconds_until as custom_rsu
from evennia.utils.create import create_script
from evennia.utils.gametime import real_seconds_until as standard_rsu

hooks = []
event_types = []

def get_event_handler():
    """Return the event handler or None."""
    try:
        script = ScriptDB.objects.get(db_key="event_handler")
    except ScriptDB.DoesNotExist:
        logger.log_err("Can't get the event handler.")
        script = None

    return script

def create_event_type(typeclass, event_name, variables, help_text,
        custom_add=None):
    """
    Create a new event type for a specific typeclass.

    Args:
        typeclass (type): the class defining tye typeclass to be used.
        event_name (str): the name of the event to be added.
        variables (list of str): a list of variable names.
        help_text (str): a help text of the event.
        custom_add (function, default None): a callback to call when adding
                the new event.

    Events obey the inheritance hierarchy: if you set an event on
    DefaultRoom, for instance, and if your Room typeclass inherits
    from DefaultRoom (the default), the event will be available to
    all rooms.  Objects of the typeclass set in argument will be
    able to set one or more events of that name.

    If the event already exists in the typeclass, replace it.

    """
    typeclass_name = typeclass.__module__ + "." + typeclass.__name__
    event_types.append((typeclass_name, event_name, variables, help_text,
            custom_add))

def del_event_type(typeclass, event_name):
    """
    Delete the event type for this typeclass.

    Args:
        typeclass (type): the class defining the typeclass.
        event_name (str): the name of the event to be deleted.

    If you want to delete an event type, you need to remove it from
    the typeclass that defined it: other typeclasses in the inheritance
    hierarchy are not affected.  This method doesn't remove the
    already-created events associated with individual objects.

    """
    typeclass_name = typeclass.__module__ + "." + typeclass.__name__
    try:
        script = ScriptDB.objects.get(db_key="event_handler")
    except ScriptDB.DoesNotExist:
        logger.log_err("Can't create event {} in typeclass {}, the " \
                "script handler isn't defined".format(name, typeclass_name))
        return

    # Get the event types for this typeclass
    event_types = script.ndb.event_types.get(typeclass_name, {})
    if event_name in event_types:
        del event_types[event_name]

def patch_hook(typeclass, method_name):
    """Decorator to softly patch a hook in a typeclass."""
    hook = getattr(typeclass, method_name)
    def wrapper(method):
        """Wrapper around the hook."""
        def overridden_hook(*args, **kwargs):
            """Function to call the new hook."""
            # Enforce the old hook as a keyword argument
            kwargs["hook"] = hook
            ret = method(*args, **kwargs)
            return ret
        hooks.append((typeclass, method_name, overridden_hook))
        return overridden_hook
    return wrapper

def patch_hooks():
    """
    Patch all the configured hooks.

    This function should be called only once when the event system
    has loaded, is set and has defined its patched typeclasses.
    It will be called internally by the event system, you shouldn't
    call this function in your game.

    """
    while hooks:
        typeclass, method_name, new_hook = hooks[0]
        setattr(typeclass, method_name, new_hook)
        del hooks[0]

def connect_event_types():
    """
    Connect the event types when the script runs.

    This method should be called automatically by the event handler
    (the script).

    """
    try:
        script = ScriptDB.objects.get(db_key="event_handler")
    except ScriptDB.DoesNotExist:
        logger.log_err("Can't connect event types, the event handler " \
                "cannot be found.")
        return

    for typeclass_name, event_name, variables, help_text, \
            custom_add in event_types:
        # Get the event types for this typeclass
        if typeclass_name not in script.ndb.event_types:
            script.ndb.event_types[typeclass_name] = {}
        types = script.ndb.event_types[typeclass_name]

        # Add or replace the event
        help_text = dedent(help_text.strip("\n"))
        types[event_name] = (variables, help_text, custom_add)

# Custom callbacks for specific events
def get_next_wait(format):
    """
    Get the length of time in seconds before format.

    Args:
        format (str): a time format matching the set calendar.

    The time format could be something like "2018-01-08 12:00".  The
    number of units set in the calendar affects the way seconds are
    calculated.

    """
    calendar = getattr(settings, "EVENTS_CALENDAR", None)
    if calendar is None:
        logger.log_err("A time-related event has been set whereas " \
                "the gametime calendar has not been set in the settings.")
        return
    elif calendar == "standard":
        rsu = standard_rsu
        units = ["min", "hour", "day", "month", "year"]
    elif calendar == "custom":
        rsu = custom_rsu
        back = dict([(value, name) for name, value in UNITS.items()])
        sorted_units = sorted(back.items())
        del sorted_units[0]
        units = [n for v, n in sorted_units]

    params = {}
    for delimiter in ("-", ":"):
        format = format.replace(delimiter, " ")

    pieces = list(reversed(format.split()))
    details = []
    i = 0
    for uname in units:
        try:
            piece = pieces[i]
        except IndexError:
            break

        if not piece.isdigit():
            logger.log_err("The time specified '{}' in {} isn't " \
                    "a valid number".format(piece, format))
            return

        # Convert the piece to int
        piece = int(piece)
        params[uname] = piece
        details.append("{}={}".format(uname, piece))
        i += 1

    params["sec"] = 0
    details = " ".join(details)
    seconds = rsu(**params)
    return seconds, details

def create_time_event(obj, event_name, number, parameters):
    """
    Create an time-related event.

    args:
        obj (Object): the object on which stands the event.
        event_name (str): the event's name.
        number (int): the number of the event.
        parameter (str): the parameter of the event.

    """
    print "parameters", repr(parameters)
    seconds, key = get_next_wait(parameters)
    script = create_script("evennia.contrib.events.scripts.TimeEventScript", interval=seconds, obj=obj)
    script.key = key
    script.desc = "time event called regularly on {}".format(key)
    script.db.time_format = parameters
    script.db.number = number
