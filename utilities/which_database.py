#!/usr/bin/env python

"""which_database

This little script checks which database is used to save your data, and
also prints out information about which database systems are available.

It will check whichever database you have setup to use in the [Storage]
persistent_storage_file option.

Note that you will end up with extra files after running this utility
that may be safely deleted:
  o dumbdb.dir
  o dumbdb.dat
  o dumbdb.bak
  o bsddb3
  o dbhash
"""

__author__ = "Remi Ricard <papaDoc@videotron.ca>"
__credits__ = "Skip Montanaro, all the Spambayes folk."

import os
import sys

sys.path.insert(-1, os.getcwd())
sys.path.insert(-1, os.path.dirname(os.getcwd()))

from spambayes.Options import options
import dumbdbm
import dbhash
import whichdb
try:
    import bsddb
except ImportError:
    try:
        import bsddb3 as bsddb
    except ImportError:
        bsddb = None

def main():
    print "Pickle is available."
    db = dumbdbm.open("dumbdb", "c")
    db["1"] = "1"
    db.close()
    str = whichdb.whichdb("dumbdb")
    if str:
        print "Dumbdbm is available."
    else:
        print "Dumbdbm is not available."

    db = dbhash.open("dbhash", "c")
    db["1"] = "1"
    db.close()
    str = whichdb.whichdb("dbhash")
    if str == "dbhash":
        print "Dbhash is available."
    else:
        print "Dbhash is not available."

    if bsddb is None:
        str = ""
    else:
        db = bsddb.hashopen("bsddb3", "c")
        db["1"] = "1"
        db.close()
        str = whichdb.whichdb("bsddb3")
    if str == "dbhash":
        print "Bsddb[3] is available."
    else:
        print "Bsddb[3] is not available."

    print

    hammie = options["Storage", "persistent_storage_file"]
    use_dbm = options["Storage", "persistent_use_database"]
    if not use_dbm:
            print "Your storage %s is a: pickle" % (hammie,)
            return

    db_type = whichdb.whichdb(hammie)
    if db_type == "dbhash":
        # could be dbhash or bsddb3
        try:
            db = dbhash.open(hammie, "c")
        except:
            print "Your storage %s is a: bsddb3" % (hammie,)
            return
    elif db_type is None:
        print "Your storage %s either does not exist, or is unreadable." % \
              (hammie,)
    print "Your storage %s is a: %s" % (hammie, db_type)

if __name__ == "__main__":
    main()
