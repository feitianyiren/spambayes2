#! /usr/bin/env python

# A test driver using "the standard" test directory structure.
# This simulates a user that gets E-mail, and only trains on fp,
# fn and unsure messages. It starts by training on the first 30
# messages, and from that point on well classified messages will
# not be used for training. This can be used to see what the performance
# of the scoring algorithm is under such conditions. Questions are:
#  * How does the size of the database behave over time?
#  * Does the classification get better over time?
#  * Are there other combinations of parameters for the classifier
#    that make this better behaved than the default values?


"""Usage: %(program)s  [options] -n nsets

Where:
    -h
        Show usage and exit.
    -n int
        Number of Set directories (Data/Spam/Set1, ... and Data/Ham/Set1, ...).
        This is required.
    -d decider 
        Name of the decider. One of %(decisionkeys)s
    -u updater
        Name of the updater. One of %(updaterkeys)s
    -m min
        Minimal number of messages to train on before involving the decider.

In addition, an attempt is made to merge bayescustomize.ini into the options.
If that exists, it can be used to change the settings in Options.options.
"""

from __future__ import generators

import sys,os

from Options import options
import hammie

import msgs
import CostCounter

program = sys.argv[0]

debug = 0

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class TrainDecision:
    def __call__(self,scr,is_spam):
        if is_spam:
            return self.spamtrain(scr)
        else:
            return self.hamtrain(scr)

class UnsureAndFalses(TrainDecision):
    def spamtrain(self,scr):
        return scr < options.spam_cutoff

    def hamtrain(self,scr):
        return scr > options.ham_cutoff

class UnsureOnly(TrainDecision):
    def spamtrain(self,scr):
        return options.ham_cutoff < scr < options.spam_cutoff

    hamtrain = spamtrain

class All(TrainDecision):
    def spamtrain(self,scr):
        return 1

    hamtrain = spamtrain

class AllBut0and100(TrainDecision):
    def spamtrain(self,scr):
        return scr < 0.995

    def hamtrain(self,scr):
        return scr > 0.005

decisions={'all': All,
           'allbut0and100': AllBut0and100,
           'unsureonly': UnsureOnly,
           'unsureandfalses': UnsureAndFalses,
          }
decisionkeys=decisions.keys()
decisionkeys.sort()

class FirstN:
    def __init__(self,n,client):
        self.client = client
        self.x = 0
        self.n = n

    def __call__(self,scr,is_spam):
        self.x += 1
        if self.tooearly():
            return True
        else:
            return self.client(scr,is_spam)
    
    def tooearly(self):
        return self.x < self.n

class Updater:
    def __init__(self,d=None):
        self.setd(d)

    def setd(self,d):
        self.d=d

class AlwaysUpdate(Updater):
    def __call__(self):
        self.d.update_probabilities()

class SometimesUpdate(Updater):
    def __init__(self,d=None,factor=10):
        Updater.__init__(self,d)
        self.factor=factor
        self.n = 0

    def __call__(self):
        self.n += 1
        if self.n % self.factor == 0:
            self.d.update_probabilities()

updaters={'always':AlwaysUpdate,
          'sometimes':SometimesUpdate,
         }
updaterkeys=updaters.keys()
updaterkeys.sort()

def drive(nsets,decision,updater):
    print options.display()

    spamdirs = [options.spam_directories % i for i in range(1, nsets+1)]
    hamdirs  = [options.ham_directories % i for i in range(1, nsets+1)]

    spamfns = [(x,y,1) for x in spamdirs for y in os.listdir(x)]
    hamfns = [(x,y,0) for x in hamdirs for y in os.listdir(x)]

    nham = len(hamfns)
    nspam = len(spamfns)
    cc = CostCounter.nodelay()

    allfns = {}
    for fn in spamfns+hamfns:
        allfns[fn] = None

    d = hammie.Hammie(hammie.createbayes('weaktest.db', False))
    updater.setd(d)

    hamtrain = 0
    spamtrain = 0
    n = 0
    for dir,name, is_spam in allfns.iterkeys():
        n += 1
        m=msgs.Msg(dir, name).guts
        if debug > 1:
            print "trained:%dH+%dS"%(hamtrain,spamtrain)
        scr=d.score(m)
        if debug > 1:
            print "score:%.3f"%scr
        if not decision.tooearly():
            if is_spam:
                if debug > 0:
                    print "Spam with score %.2f"%scr
                cc.spam(scr)
            else:
                if debug > 0:
                    print "Ham with score %.2f"%scr
                cc.ham(scr)
        if decision(scr,is_spam):
            if is_spam:
                d.train_spam(m)
                spamtrain += 1
            else:
                d.train_ham(m)
                hamtrain += 1
            updater()
        if n % 100 == 0:
            print "%5d trained:%dH+%dS wrds:%d"%(
                n, hamtrain, spamtrain, len(d.bayes.wordinfo))
            print cc
    print "="*70
    print "%5d trained:%dH+%dS wrds:%d"%(
        n, hamtrain, spamtrain, len(d.bayes.wordinfo))
    print cc

def main():
    global debug

    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'vd:u:hn:m:')
    except getopt.error, msg:
        usage(1, msg)

    nsets = None
    decision = decisions['unsureonly']
    updater = updaters['always']
    m = 10

    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)
        elif opt == '-v':
            debug += 1
        elif opt == '-m':
            m = int(arg)
        elif opt == '-d':
            if not decisions.has_key(arg):
                usage(1,'Unknown decisionmaker')
            decision = decisions[arg]
        elif opt == '-u':
            if not updaters.has_key(arg):
                usage(1,'Unknown updater')
            updater = updaters[arg]

    if args:
        usage(1, "Positional arguments not supported")
    if nsets is None:
        usage(1, "-n is required")

    drive(nsets,decision=FirstN(m,decision()),updater=updater())

if __name__ == "__main__":
    main()
