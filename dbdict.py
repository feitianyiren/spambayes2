#! /usr/bin/env python

from __future__ import generators
import dbhash
try:
    import cPickle as pickle
except ImportError:
    import pickle

class DBDict:
    """Database Dictionary.

    This wraps a dbhash database to make it look even more like a
    dictionary, much like the built-in shelf class.  The difference is
    that a DBDict supports all dict methods.

    Call it with the database.  Optionally, you can specify a list of
    keys to skip when iterating.  This only affects iterators; things
    like .keys() still list everything.  For instance:

    >>> d = DBDict('goober.db', 'c', ('skipme', 'skipmetoo'))
    >>> d['skipme'] = 'booga'
    >>> d['countme'] = 'wakka'
    >>> print d.keys()
    ['skipme', 'countme']
    >>> for k in d.iterkeys():
    ...     print k
    countme

    """

    def __init__(self, dbname, mode, iterskip=()):
        self.hash = dbhash.open(dbname, mode)
        self.iterskip = iterskip

    def __getitem__(self, key):
        return pickle.loads(self.hash[key])

    def __setitem__(self, key, val):
        self.hash[key] = pickle.dumps(val, 1)

    def __delitem__(self, key, val):
        del(self.hash[key])

    def __iter__(self, fn=None):
        k = self.hash.first()
        while k != None:
            key = k[0]
            val = self.__getitem__(key)
            if key not in self.iterskip:
                if fn:
                    yield fn((key, val))
                else:
                    yield (key, val)
            try:
                k = self.hash.next()
            except KeyError:
                break

    def __contains__(self, name):
        return self.has_key(name)

    def __getattr__(self, name):
        # Pass the buck
        return getattr(self.hash, name)

    def get(self, key, dfl=None):
        if self.has_key(key):
            return self[key]
        else:
            return dfl

    def iteritems(self):
        return self.__iter__()

    def iterkeys(self):
        return self.__iter__(lambda k: k[0])

    def itervalues(self):
        return self.__iter__(lambda k: k[1])

open = DBDict

def _test():
    import doctest
    import dbdict

    doctest.testmod(dbdict)

if __name__ == '__main__':
    _test()

