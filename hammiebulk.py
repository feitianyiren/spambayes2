#! /usr/bin/env python

"""Usage: %(program)s [-D|-d] [options]

Where:
    -h
        show usage and exit
    -d
        use the DBM store.  A DBM file is larger than the pickle and
        creating it is slower, but loading it is much faster,
        especially for large word databases.  Recommended for use with
        hammiefilter or any procmail-based filter.
    -D
        use the pickle store.  A pickle is smaller and faster to create,
        but much slower to load.  Recommended for use with pop3proxy and
        hammiesrv.
    -p FILE
        use file as the persistent store.  loads data from this file if it
        exists, and saves data to this file at the end.
        Default: %(DEFAULTDB)s

    -f
        run as a filter: read a single message from stdin, add a new
        header, and write it to stdout.  If you want to run from
        procmail, this is your option.
    -g PATH
        mbox or directory of known good messages (non-spam) to train on.
        Can be specified more than once, or use - for stdin.
    -s PATH
        mbox or directory of known spam messages to train on.
        Can be specified more than once, or use - for stdin.
    -u PATH
        mbox of unknown messages.  A ham/spam decision is reported for each.
        Can be specified more than once.
    -r
        reverse the meaning of the check (report ham instead of spam).
        Only meaningful with the -u option.
"""

import sys
import os
import types
import getopt
import mailbox
import glob
import email
import errno
import anydbm
import cPickle as pickle

from Options import options
import mboxutils
import classifier
import Persistent
import hammie
import Corpus

Corpus.Verbose = True

program = sys.argv[0] # For usage(); referenced by docstring above

# Default database name
DEFAULTDB = os.path.expanduser(options.hammiefilter_persistent_storage_file)

# Probability at which a message is considered spam
SPAM_THRESHOLD = options.spam_cutoff
HAM_THRESHOLD = options.ham_cutoff


def train(h, msgs, is_spam):
    """Train bayes with all messages from a mailbox."""
    mbox = mboxutils.getmbox(msgs)
    i = 0
    for msg in mbox:
        i += 1
        sys.stdout.write("\r%6d" % i)
        sys.stdout.flush()
        h.train(msg, is_spam)
    print

def score(h, msgs, reverse=0):
    """Score (judge) all messages from a mailbox."""
    # XXX The reporting needs work!
    mbox = mboxutils.getmbox(msgs)
    i = 0
    spams = hams = 0
    for msg in mbox:
        i += 1
        prob, clues = h.score(msg, True)
        if hasattr(msg, '_mh_msgno'):
            msgno = msg._mh_msgno
        else:
            msgno = i
        isspam = (prob >= SPAM_THRESHOLD)
        if isspam:
            spams += 1
            if not reverse:
                print "%6s %4.2f %1s" % (msgno, prob, isspam and "S" or "."),
                print h.formatclues(clues)
        else:
            hams += 1
            if reverse:
                print "%6s %4.2f %1s" % (msgno, prob, isspam and "S" or "."),
                print h.formatclues(clues)
    return (spams, hams)

def createbayes(pck=DEFAULTDB, usedb=False, mode='r'):
    """Create a Bayes instance for the given pickle (which
    doesn't have to exist).  Create a PersistentBayes if
    usedb is True."""
    if usedb:
        bayes = Persistent.DBDictClassifier(pck, mode)
    else:
        bayes = Persistent.PickledClassifier(pck)
    return bayes

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    """Main program; parse options and go."""
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hdDfg:s:p:u:r')
    except getopt.error, msg:
        usage(2, msg)

    if not opts:
        usage(2, "No options given")

    pck = DEFAULTDB
    good = []
    spam = []
    unknown = []
    reverse = 0
    do_filter = False
    usedb = None
    mode = 'r'
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-g':
            good.append(arg)
            mode = 'c'
        elif opt == '-s':
            spam.append(arg)
            mode = 'c'
        elif opt == '-p':
            pck = arg
        elif opt == "-d":
            usedb = True
        elif opt == "-D":
            usedb = False
        elif opt == "-f":
            do_filter = True
        elif opt == '-u':
            unknown.append(arg)
        elif opt == '-r':
            reverse = 1
    if args:
        usage(2, "Positional arguments not allowed")

    if usedb == None:
        usage(2, "Must specify one of -d or -D")

    save = False

    h = hammie.open(pck, usedb, mode)

    for g in good:
        print "Training ham (%s):" % g
        train(h, g, False)
        save = True

    for s in spam:
        print "Training spam (%s):" % s
        train(h, s, True)
        save = True

    if save:
        h.store()

    if do_filter:
        msg = sys.stdin.read()
        filtered = h.filter(msg)
        sys.stdout.write(filtered)

    if unknown:
        (spams, hams) = (0, 0)
        for u in unknown:
            if len(unknown) > 1:
                print "Scoring", u
            s, g = score(h, u, reverse)
            spams += s
            hams += g
        print "Total %d spam, %d ham" % (spams, hams)

if __name__ == "__main__":
    main()
