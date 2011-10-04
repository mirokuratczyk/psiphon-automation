#!/usr/bin/python
#
# Copyright (c) 2011, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys
from textwrap import dedent
from keyword import iskeyword


# Adapted from:
# http://code.activestate.com/recipes/576555/
# (Our only change is the log property)

__all__ = ['recordtype']

def recordtype(typename, field_names, verbose=False, **default_kwds):
    '''Returns a new class with named fields.

    @keyword field_defaults: A mapping from (a subset of) field names to default
        values.
    @keyword default: If provided, the default value for all fields without an
        explicit default in `field_defaults`.

    >>> Point = recordtype('Point', 'x y', default=0)
    >>> Point.__doc__           # docstring for the new class
    'Point(x, y)'
    >>> Point()                 # instantiate with defaults
    Point(x=0, y=0)
    >>> p = Point(11, y=22)     # instantiate with positional args or keywords
    >>> p[0] + p.y              # accessible by name and index
    33
    >>> p.x = 100; p[1] =200    # modifiable by name and index
    >>> p
    Point(x=100, y=200)
    >>> x, y = p               # unpack
    >>> x, y
    (100, 200)
    >>> d = p.todict()         # convert to a dictionary
    >>> d['x']
    100
    >>> Point(**d) == p        # convert from a dictionary
    True
    '''
    # Parse and validate the field names.  Validation serves two purposes,
    # generating informative error messages and preventing template injection attacks.
    if isinstance(field_names, basestring):
        # names separated by whitespace and/or commas
        field_names = field_names.replace(',', ' ').split()
    field_names = tuple(map(str, field_names))
    if not field_names:
        raise ValueError('Records must have at least one field')
    for name in (typename,) + field_names:
        if not min(c.isalnum() or c=='_' for c in name):
            raise ValueError('Type names and field names can only contain '
                             'alphanumeric characters and underscores: %r' % name)
        if iskeyword(name):
            raise ValueError('Type names and field names cannot be a keyword: %r'
                             % name)
        if name[0].isdigit():
            raise ValueError('Type names and field names cannot start with a '
                             'number: %r' % name)
    seen_names = set()
    for name in field_names:
        if name.startswith('_'):
            raise ValueError('Field names cannot start with an underscore: %r'
                             % name)
        if name in seen_names:
            raise ValueError('Encountered duplicate field name: %r' % name)
        seen_names.add(name)
    # determine the func_defaults of __init__
    field_defaults = default_kwds.pop('field_defaults', {})
    if 'default' in default_kwds:
        default = default_kwds.pop('default')
        init_defaults = tuple(field_defaults.get(f,default) for f in field_names)
    elif not field_defaults:
        init_defaults = None
    else:
        default_fields = field_names[-len(field_defaults):]
        if set(default_fields) != set(field_defaults):
            raise ValueError('Missing default parameter values')
        init_defaults = tuple(field_defaults[f] for f in default_fields)
    if default_kwds:
        raise ValueError('Invalid keyword arguments: %s' % default_kwds)
    # Create and fill-in the class template
    numfields = len(field_names)
    argtxt = ', '.join(field_names)
    reprtxt = ', '.join('%s=%%r' % f for f in field_names)
    dicttxt = ', '.join('%r: self.%s' % (f,f) for f in field_names)
    tupletxt = repr(tuple('self.%s' % f for f in field_names)).replace("'",'')
    inittxt = '; '.join('self.%s=%s' % (f,f) for f in field_names)
    itertxt = '; '.join('yield self.%s' % f for f in field_names)
    eqtxt   = ' and '.join('self.%s==other.%s' % (f,f) for f in field_names)
    template = dedent('''
        class %(typename)s(object):
            '%(typename)s(%(argtxt)s)'

            __slots__  = %(field_names)r

            def __init__(self, %(argtxt)s):
                %(inittxt)s
                self.__log = []

            def log(self, message):
                self.__log.append((time.time(), message))

            def get_log(self):
                return self.__log

            def __len__(self):
                return %(numfields)d

            def __iter__(self):
                %(itertxt)s

            def __getitem__(self, index):
                return getattr(self, self.__slots__[index])

            def __setitem__(self, index, value):
                return setattr(self, self.__slots__[index], value)

            def todict(self):
                'Return a new dict which maps field names to their values'
                return {%(dicttxt)s}

            def __repr__(self):
                return '%(typename)s(%(reprtxt)s)' %% %(tupletxt)s

            def __eq__(self, other):
                return isinstance(other, self.__class__) and %(eqtxt)s

            def __ne__(self, other):
                return not self==other

            def __getstate__(self):
                return %(tupletxt)s

            def __setstate__(self, state):
                %(tupletxt)s = state
    ''') % locals()
    # Execute the template string in a temporary namespace
    namespace = {}
    try:
        exec template in namespace
        if verbose: print template
    except SyntaxError, e:
        raise SyntaxError(e.message + ':\n' + template)
    cls = namespace[typename]
    cls.__init__.im_func.func_defaults = init_defaults
    # For pickling to work, the __module__ variable needs to be set to the frame
    # where the named tuple is created.  Bypass this step in enviroments where
    # sys._getframe is not defined (Jython for example).
    if hasattr(sys, '_getframe') and sys.platform != 'cli':
        cls.__module__ = sys._getframe(1).f_globals['__name__']
    return cls


# Adapted from:
# http://code.activestate.com/recipes/521901-upgradable-pickles/

class PersistentObject(object):

    class_version = '0.0'

    def __init__(self):
        self.version = self.__class__.class_version

    def save(self, filename):
        with open(filename, 'wb') as file:
            file.write(cPickle.dumps(self))

    @staticmethod
    def load(filename):
        with open(filename, 'rb') as file:
            obj = cPickle.loads(file.read())
            if not hasattr(obj, 'version'):
                obj.version = '0.0'
            if obj.version != obj.class_version:
                obj.upgrade()
            returnobj

    def upgrade(self):
        pass 
