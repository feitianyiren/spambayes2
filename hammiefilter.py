#!/usr/bin/env python

## A hammie front-end to make the simple stuff simple.
##
##
## The intent is to call this from procmail and its ilk like so:
##
##   :0 fw
##   | hammiefilter.py
## 
## Then, you can set up your MUA to pipe ham and spam to it, one at a
## time, by calling it with either the -g or -s options, respectively.
##
## Author: Neale Pickett <neale@woozle.org>
##

"""Usage: %(program)s [OPTION]...

A hammie front-end to make the simple stuff simple.  The intent is to call
this from procmail and its ilk like so:

  :0 fw
  | hammiefilter.py

Then, you can set up your MUA to pipe ham and spam to it, one at a time, by
calling it with either the -g or -s options, respectively.

[OPTION] is one of:
    -h
        show usage and exit
    -d DBFILE
        use database in DBFILE
    -D PICKLEFILE
        use pickle (instead of database) in PICKLEFILE
    -n
        create a new database
    -g
        train as a good (ham) message
    -s
        train as a bad (spam) message
    -t
        filter and train based on the result (you must make sure to
        untrain all mistakes later)
    -G
        untrain ham (only use if you've already trained this message)
    -S
        untrain spam (only use if you've already trained this message)

All processing options operate on stdin.  If no processing options are
given, stdin will be scored: the same message, with a new header
containing the score, will be send to stdout.

"""

import os
import sys
import getopt
from spambayes import hammie, Options, mboxutils

# See Options.py for explanations of these properties
program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class HammieFilter(object):
    def __init__(self):
        options = Options.options
        options.mergefiles(['/etc/hammierc',
                            os.path.expanduser('~/.hammierc')])
        self.dbname = options.hammiefilter_persistent_storage_file
        self.dbname = os.path.expanduser(self.dbname)
        self.usedb = options.hammiefilter_persistent_use_database

    def newdb(self):
        h = hammie.open(self.dbname, self.usedb, 'n')
        h.store()
        print "Created new database in", self.dbname

    def filter(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'r')
        print h.filter(msg)

    def filter_train(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        print h.filter(msg, train=True)

    def train_ham(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.train_ham(msg)
        h.store()

    def train_spam(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.train_spam(msg)
        h.store()

    def untrain_ham(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.untrain_ham(msg)
        h.store()

    def untrain_spam(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.untrain_spam(msg)
        h.store()

def main():
    h = HammieFilter()
    actions = []
    opts, args = getopt.getopt(sys.argv[1:], 'hd:D:ngstGS', ['help'])
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(0)
        elif opt == '-d':
            h.usedb = True
            h.dbname = arg
        elif opt == '-D':
            h.usedb = False
            h.dbname = arg
        elif opt == '-g':
            actions.append(h.train_ham)
        elif opt == '-s':
            actions.append(h.train_spam)
        elif opt == '-t':
            actions.append(h.filter_train)
        elif opt == '-G':
            actions.append(h.untrain_ham)
        elif opt == '-S':
            actions.append(h.untrain_spam)
        elif opt == "-n":
            h.newdb()
            sys.exit(0)

    if actions == []:
        actions = [h.filter]

    msg = mboxutils.get_message(sys.stdin)
    for action in actions:
        action(msg)


if __name__ == "__main__":
    main()

