#! /usr/bin/env python

'''Persistent.py - Spambayes database management framework.

Classes:
    PersistentClassifier - subclass of Classifier, adds auto persistence
    PickledClassifier - PersistentClassifier that uses a pickle db
    DBDictClassifier - PersistentClassifier that uses a DBDict db
    Trainer - Classifier training observer
    SpamTrainer - Trainer for spam
    HamTrainer - Trainer for ham

Abstract:
    PersistentClassifier is an abstract subclass of Classifier (classifier.Classifier)
    that adds automatic state store/restore function to the Classifier class.
    It also adds a convenience method, which should probably
    more properly be defined in Classifier: classify, which returns
    'spam'|'ham'|'unsure' for a message based on the spamprob against
    the ham_cutoff and spam_cutoff specified in Options.

    PickledClassifier is a concrete PersistentClassifier class that uses a cPickle
    datastore.  This database is relatively small, but slower than other
    databases.

    DBDictClassifier is a concrete PersistentClassifier class that uses a DBDict
    datastore.

    Trainer is concrete class that observes a Corpus and trains a
    Classifier object based upon movement of messages between corpora  When
    an add message notification is received, the trainer trains the
    database with the message, as spam or ham as appropriate given the
    type of trainer (spam or ham).  When a remove message notification
    is received, the trainer untrains the database as appropriate.

    SpamTrainer and HamTrainer are convenience subclasses of Trainer, that
    initialize as the appropriate type of Trainer

To Do:
    o ZODBClassifier
    o Would Trainer.trainall really want to train with the whole corpus,
        or just a random subset?
    o Suggestions?

    '''

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "Richie Hindle, Tim Peters, Neale Pickett, \
all the spambayes contributors."

import classifier
from Options import options
import cPickle as pickle
import dbdict
import errno

PICKLE_TYPE = 1
NO_UPDATEPROBS = False   # Probabilities will not be autoupdated with training
UPDATEPROBS = True       # Probabilities will be autoupdated with training

class PersistentClassifier(classifier.Classifier):
    '''Persistent Classifier database object'''

    def __init__(self, db_name):
        '''Constructor(database name)'''

        classifier.Classifier.__init__(self)
        self.db_name = db_name
        self.load()

    def load(self):
        '''Restore state from a persistent store'''

        raise NotImplementedError

    def store(self):
        '''Persist state into a persistent store'''

        raise NotImplementedError

    def classify(self, message):
        '''Returns the classification of a Message {'spam'|'ham'|'unsure'}'''

        prob = self.spamprob(message.tokenize())

        message.setSpamprob(prob)   # don't like this

        if prob < options.ham_cutoff:
            type = 'ham'
        elif prob > options.spam_cutoff:
            type = 'spam'
        else:
            type = 'unsure'

        return type


class PickledClassifier(PersistentClassifier):
    '''Classifier object persisted in a pickle'''

    def load(self):
        '''Load this instance from the pickle.'''
        # This is a bit strange, because the loading process
        # creates a temporary instance of PickledClassifier, from which
        # this object's state is copied.  This is a nuance of the way
        # that pickle does its job

        if False and __debug__:
            print 'Loading state from',self.db_name,'pickle'

        tempbayes = None
        try:
            fp = open(self.db_name, 'rb')
        except IOError, e:
            if e.errno != errno.ENOENT: raise
        else:
            tempbayes = pickle.load(fp)
            fp.close()

        if tempbayes:
            self.wordinfo = tempbayes.wordinfo
            self.meta.nham = tempbayes.get_nham()
            self.meta.nspam = tempbayes.get_nspam()

            if False and __debug__:
                print '%s is an existing pickle, with %d ham and %d spam' \
                      % (self.db_name, self.nham, self.nspam)
        else:
            # new pickle
            if False and __debug__:
                print self.db_name,'is a new pickle'
            self.wordinfo = {}
            self.meta.nham = 0
            self.meta.nspam = 0

    def store(self):
        '''Store self as a pickle'''

        if False and __debug__:
            print 'Persisting',self.db_name,'as a pickle'

        fp = open(self.db_name, 'wb')
        pickle.dump(self, fp, PICKLE_TYPE)
        fp.close()

    def __getstate__(self):
        return PICKLE_TYPE, self.wordinfo, self.meta

    def __setstate__(self, t):
        if t[0] != PICKLE_TYPE:
            raise ValueError("Can't unpickle -- version %s unknown" % t[0])
        self.wordinfo, self.meta = t[1:]


class DBDictClassifier(PersistentClassifier):
    '''Classifier object persisted in a WIDict'''

    def __init__(self, db_name, mode='c'):
        '''Constructor(database name)'''

        self.mode = mode
        self.statekey = "saved state"
        PersistentClassifier.__init__(self, db_name)

    def load(self):
        '''Load state from WIDict'''

        if False and __debug__:
            print 'Loading state from',self.db_name,'WIDict'

        self.wordinfo = dbdict.DBDict(self.db_name, self.mode,
                             classifier.WordInfo,iterskip=[self.statekey])

        if self.wordinfo.has_key(self.statekey):
            (nham, nspam) = self.wordinfo[self.statekey]
            self.set_nham(nham)
            self.set_nspam(nspam)

            if False and __debug__:
                print '%s is an existing DBDict, with %d ham and %d spam' \
                      % (self.db_name, self.nham, self.nspam)
        else:
            # new dbdict
            if False and __debug__:
                print self.db_name,'is a new DBDict'
            self.set_nham(0)
            self.set_nspam(0)

    def store(self):
        '''Place state into persistent store'''

        if False and __debug__:
            print 'Persisting',self.db_name,'state in WIDict'

        self.wordinfo[self.statekey] = (self.get_nham(), self.get_nspam())
        self.wordinfo.sync()


class Trainer:
    '''Associates a Classifier object and one or more Corpora, \
    is an observer of the corpora'''

    def __init__(self, bayes, is_spam, updateprobs=NO_UPDATEPROBS):
        '''Constructor(Classifier, is_spam(True|False), updprobs(True|False)'''

        self.bayes = bayes
        self.is_spam = is_spam
        self.updateprobs = updateprobs

    def onAddMessage(self, message):
        '''A message is being added to an observed corpus.'''

        self.train(message)

    def train(self, message):
        '''Train the database with the message'''

        if False and __debug__:
            print 'training with',message.key()

        self.bayes.learn(message.tokenize(), self.is_spam)
#                         self.updateprobs)

    def onRemoveMessage(self, message):
        '''A message is being removed from an observed corpus.'''

        self.untrain(message)

    def untrain(self, message):
        '''Untrain the database with the message'''

        if False and __debug__:
            print 'untraining with',message.key()

        self.bayes.unlearn(message.tokenize(), self.is_spam)
#                           self.updateprobs)
        # can raise ValueError if database is fouled.  If this is the case,
        # then retraining is the only recovery option.

    def trainAll(self, corpus):
        '''Train all the messages in the corpus'''

        for msg in corpus:
            self.train(msg)

    def untrainAll(self, corpus):
        '''Untrain all the messages in the corpus'''

        for msg in corpus:
            self.untrain(msg)


class SpamTrainer(Trainer):
    '''Trainer for spam'''

    def __init__(self, bayes, updateprobs=NO_UPDATEPROBS):
        '''Constructor'''

        Trainer.__init__(self, bayes, True, updateprobs)


class HamTrainer(Trainer):
    '''Trainer for ham'''

    def __init__(self, bayes, updateprobs=NO_UPDATEPROBS):
        '''Constructor'''

        Trainer.__init__(self, bayes, False, updateprobs)


if __name__ == '__main__':
    print >>sys.stderr, __doc__
