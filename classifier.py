# An implementation of a Bayes-like spam classifier.
#
# Paul Graham's original description:
#
#     http://www.paulgraham.com/spam.html
#
# A highly fiddled version of that can be retrieved from our CVS repository,
# via tag Last-Graham.  This made many demonstrated improvements in error
# rates over Paul's original description.
#
# This code implements Gary Robinson's suggestions, which are well explained
# on his webpage:
#
#    http://radio.weblogs.com/0101454/stories/2002/09/16/spamDetection.html
#
# This is theoretically cleaner, and in testing has performed at least as
# well as our highly tuned Graham scheme did, often slightly better, and
# sometimes much better.  It also has "a middle ground", which people like:
# the scores under Paul's scheme were almost always very near 0 or very near
# 1, whether or not the classification was correct.  The false positives
# and false negatives under Gary's scheme generally score in a narrow range
# around the corpus's best spam_cutoff value
#
# This implementation is due to Tim Peters et alia.

import time
from sets import Set

from Options import options
if options.use_chi_squared_combining:
    from chi2 import chi2Q
if options.use_z_combining:
    from chi2 import normP, normIP

# The maximum number of extreme words to look at in a msg, where "extreme"
# means with spamprob farthest away from 0.5.
MAX_DISCRIMINATORS = options.max_discriminators # 150

PICKLE_VERSION = 1

class WordInfo(object):
    __slots__ = ('atime',     # when this record was last used by scoring(*)
                 'spamcount', # # of spams in which this word appears
                 'hamcount',  # # of hams in which this word appears
                 'killcount', # # of times this made it to spamprob()'s nbest
                 'spamprob',  # prob(spam | msg contains this word)
                )

    # Invariant:  For use in a classifier database, at least one of
    # spamcount and hamcount must be non-zero.
    #
    # (*)atime is the last access time, a UTC time.time() value.  It's the
    # most recent time this word was used by scoring (i.e., by spamprob(),
    # not by training via learn()); or, if the word has never been used by
    # scoring, the time the word record was created (i.e., by learn()).
    # One good criterion for identifying junk (word records that have no
    # value) is to delete words that haven't been used for a long time.
    # Perhaps they were typos, or unique identifiers, or relevant to a
    # once-hot topic or scam that's fallen out of favor.  Whatever, if
    # a word is no longer being used, it's just wasting space.

    def __init__(self, atime, spamprob=None):
        self.atime = atime
        self.spamcount = self.hamcount = self.killcount = 0
        self.spamprob = spamprob

    def __repr__(self):
        return "WordInfo%r" % repr((self.atime, self.spamcount,
                                    self.hamcount, self.killcount,
                                    self.spamprob))

    def __getstate__(self):
        return (self.atime, self.spamcount, self.hamcount, self.killcount,
                self.spamprob)

    def __setstate__(self, t):
        (self.atime, self.spamcount, self.hamcount, self.killcount,
         self.spamprob) = t

class Bayes(object):
    __slots__ = ('wordinfo',  # map word to WordInfo record
                 'nspam',     # number of spam messages learn() has seen
                 'nham',      # number of non-spam messages learn() has seen

                 # The rest is unique to the central-limit code.
                 # n is the # of data points in the population.
                 # sum is the sum of the probabilities, and is a long scaled
                 # by 2**64.
                 # sumsq is the sum of the squares of the probabilities, and
                 # is a long scaled by 2**128.
                 # mean is the mean probability of the population, as an
                 # unscaled float.
                 # var is the variance of the population, as unscaled float.
                 # There's one set of these for the spam population, and
                 # another for the ham population.
                 # XXX If this code survives, clean it up.
                 'spamn',
                 'spamsum',
                 'spamsumsq',
                 'spammean',
                 'spamvar',

                 'hamn',
                 'hamsum',
                 'hamsumsq',
                 'hammean',
                 'hamvar',
                )

    def __init__(self):
        self.wordinfo = {}
        self.nspam = self.nham = 0
        self.spamn = self.hamn = 0
        self.spamsum = self.spamsumsq = 0
        self.hamsum = self.hamsumsq = 0

    def __getstate__(self):
        return PICKLE_VERSION, self.wordinfo, self.nspam, self.nham

    def __setstate__(self, t):
        if t[0] != PICKLE_VERSION:
            raise ValueError("Can't unpickle -- version %s unknown" % t[0])
        self.wordinfo, self.nspam, self.nham = t[1:]

    def spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import frexp

        # This combination method is due to Gary Robinson; see
        # http://radio.weblogs.com/0101454/stories/2002/09/16/spamDetection.html

        # The real P = this P times 2**Pexp.  Likewise for Q.  We're
        # simulating unbounded dynamic float range by hand.  If this pans
        # out, *maybe* we should store logarithms in the database instead
        # and just add them here.  But I like keeping raw counts in the
        # database (they're easy to understand, manipulate and combine),
        # and there's no evidence that this simulation is a significant
        # expense.
        P = Q = 1.0
        Pexp = Qexp = 0
        clues = self._getclues(wordstream)
        for prob, word, record in clues:
            if record is not None:  # else wordinfo doesn't know about it
                record.killcount += 1
            P *= 1.0 - prob
            Q *= prob
            if P < 1e-200:  # move back into range
                P, e = frexp(P)
                Pexp += e
            if Q < 1e-200:  # move back into range
                Q, e = frexp(Q)
                Qexp += e

        P, e = frexp(P)
        Pexp += e
        Q, e = frexp(Q)
        Qexp += e

        num_clues = len(clues)
        if num_clues:
            #P = 1.0 - P**(1./num_clues)
            #Q = 1.0 - Q**(1./num_clues)
            #
            # (x*2**e)**n = x**n * 2**(e*n)
            n = 1.0 / num_clues
            P = 1.0 - P**n * 2.0**(Pexp * n)
            Q = 1.0 - Q**n * 2.0**(Qexp * n)

            prob = (P-Q)/(P+Q)  # in -1 .. 1
            prob = 0.5 + prob/2 # shift to 0 .. 1
        else:
            prob = 0.5

        if evidence:
            clues = [(w, p) for p, w, r in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            return prob, clues
        else:
            return prob

    def learn(self, wordstream, is_spam, update_probabilities=True):
        """Teach the classifier by example.

        wordstream is a word stream representing a message.  If is_spam is
        True, you're telling the classifier this message is definitely spam,
        else that it's definitely not spam.

        If optional arg update_probabilities is False (the default is True),
        don't update word probabilities.  Updating them is expensive, and if
        you're going to pass many messages to learn(), it's more efficient
        to pass False here and call update_probabilities() once when you're
        done -- or to call learn() with update_probabilities=True when
        passing the last new example.  The important thing is that the
        probabilities get updated before calling spamprob() again.
        """

        self._add_msg(wordstream, is_spam)
        if update_probabilities:
            self.update_probabilities()

    def unlearn(self, wordstream, is_spam, update_probabilities=True):
        """In case of pilot error, call unlearn ASAP after screwing up.

        Pass the same arguments you passed to learn().
        """

        self._remove_msg(wordstream, is_spam)
        if update_probabilities:
            self.update_probabilities()

    def update_probabilities(self):
        """Update the word probabilities in the spam database.

        This computes a new probability for every word in the database,
        so can be expensive.  learn() and unlearn() update the probabilities
        each time by default.  Thay have an optional argument that allows
        to skip this step when feeding in many messages, and in that case
        you should call update_probabilities() after feeding the last
        message and before calling spamprob().
        """

        nham = float(self.nham or 1)
        nspam = float(self.nspam or 1)

        S = options.robinson_probability_s
        StimesX = S * options.robinson_probability_x

        for word, record in self.wordinfo.iteritems():
            # Compute prob(msg is spam | msg contains word).
            # This is the Graham calculation, but stripped of biases, and
            # stripped of clamping into 0.01 thru 0.99.  The Bayesian
            # adjustment following keeps them in a sane range, and one
            # that naturally grows the more evidence there is to back up
            # a probability.
            hamcount = record.hamcount
            assert hamcount <= nham
            hamratio = hamcount / nham

            spamcount = record.spamcount
            assert spamcount <= nspam
            spamratio = spamcount / nspam

            prob = spamratio / (hamratio + spamratio)

            # Now do Robinson's Bayesian adjustment.
            #
            #         s*x + n*p(w)
            # f(w) = --------------
            #           s + n
            #
            # I find this easier to reason about like so (equivalent when
            # s != 0):
            #
            #        x - p
            #  p +  -------
            #       1 + n/s
            #
            # IOW, it moves p a fraction of the distance from p to x, and
            # less so the larger n is, or the smaller s is.

            n = hamcount + spamcount
            prob = (StimesX + n * prob) / (S + n)

            if record.spamprob != prob:
                record.spamprob = prob
                # The next seemingly pointless line appears to be a hack
                # to allow a persistent db to realize the record has changed.
                self.wordinfo[word] = record

    def clearjunk(self, oldesttime):
        """Forget useless wordinfo records.  This can shrink the database size.

        A record for a word will be retained only if the word was accessed
        at or after oldesttime.
        """

        wordinfo = self.wordinfo
        mincount = float(mincount)
        tonuke = [w for w, r in wordinfo.iteritems() if r.atime < oldesttime]
        for w in tonuke:
            del wordinfo[w]

    # NOTE:  Graham's scheme had a strange asymmetry:  when a word appeared
    # n>1 times in a single message, training added n to the word's hamcount
    # or spamcount, but predicting scored words only once.  Tests showed
    # that adding only 1 in training, or scoring more than once when
    # predicting, hurt under the Graham scheme.
    # This isn't so under Robinson's scheme, though:  results improve
    # if training also counts a word only once.  The mean ham score decreases
    # significantly and consistently, ham score variance decreases likewise,
    # mean spam score decreases (but less than mean ham score, so the spread
    # increases), and spam score variance increases.
    # I (Tim) speculate that adding n times under the Graham scheme helped
    # because it acted against the various ham biases, giving frequently
    # repeated spam words (like "Viagra") a quick ramp-up in spamprob; else,
    # adding only once in training, a word like that was simply ignored until
    # it appeared in 5 distinct training hams.  Without the ham-favoring
    # biases, though, and never ignoring words, counting n times introduces
    # a subtle and unhelpful bias.
    # There does appear to be some useful info in how many times a word
    # appears in a msg, but distorting spamprob doesn't appear a correct way
    # to exploit it.
    def _add_msg(self, wordstream, is_spam):
        if is_spam:
            self.nspam += 1
        else:
            self.nham += 1

        wordinfo = self.wordinfo
        wordinfoget = wordinfo.get
        now = time.time()
        for word in Set(wordstream):
            record = wordinfoget(word)
            if record is None:
                record = wordinfo[word] = WordInfo(now)

            if is_spam:
                record.spamcount += 1
            else:
                record.hamcount += 1
            wordinfo[word] = record

    def _remove_msg(self, wordstream, is_spam):
        if is_spam:
            if self.nspam <= 0:
                raise ValueError("spam count would go negative!")
            self.nspam -= 1
        else:
            if self.nham <= 0:
                raise ValueError("non-spam count would go negative!")
            self.nham -= 1

        wordinfoget = self.wordinfo.get
        for word in Set(wordstream):
            record = wordinfoget(word)
            if record is not None:
                if is_spam:
                    if record.spamcount > 0:
                        record.spamcount -= 1
                else:
                    if record.hamcount > 0:
                        record.hamcount -= 1
                if record.hamcount == 0 == record.spamcount:
                    del self.wordinfo[word]

    def compute_population_stats(self, msgstream, is_spam):
        pass

    def _getclues(self, wordstream):
        mindist = options.robinson_minimum_prob_strength
        unknown = options.robinson_probability_x

        clues = []  # (distance, prob, word, record) tuples
        pushclue = clues.append

        wordinfoget = self.wordinfo.get
        now = time.time()
        for word in Set(wordstream):
            record = wordinfoget(word)
            if record is None:
                prob = unknown
            else:
                record.atime = now
                prob = record.spamprob
            distance = abs(prob - 0.5)
            if distance >= mindist:
                pushclue((distance, prob, word, record))

        clues.sort()
        if len(clues) > options.max_discriminators:
            del clues[0 : -options.max_discriminators]
        # Return (prob, word, record).
        return [t[1:] for t in clues]

    #************************************************************************
    # Some options change so much behavior that it's better to write a
    # different method.
    # CAUTION:  These end up overwriting methods of the same name above.
    # A subclass would be cleaner, but experiments will soon enough lead
    # to only one of the alternatives surviving.

    def tim_spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import frexp

        # The real H = this H times 2**Hexp.  Likewise for S.  We're
        # simulating unbounded dynamic float range by hand.  If this pans
        # out, *maybe* we should store logarithms in the database instead
        # and just add them here.  But I like keeping raw counts in the
        # database (they're easy to understand, manipulate and combine),
        # and there's no evidence that this simulation is a significant
        # expense.
        # S is a spamminess measure, and is the geometric mean of the
        # extreme-word spamprobs.
        # H is a hamminess measure, and is the geometric mean of 1 - the
        # extreme-word spamprobs.
        H = S = 1.0
        Hexp = Sexp = 0
        clues = self._getclues(wordstream)
        for prob, word, record in clues:
            if record is not None:  # else wordinfo doesn't know about it
                record.killcount += 1
            S *= prob
            H *= 1.0 - prob
            if S < 1e-200:  # move back into range
                S, e = frexp(S)
                Sexp += e
            if H < 1e-200:  # move back into range
                H, e = frexp(H)
                Hexp += e

        S, e = frexp(S)
        Sexp += e
        H, e = frexp(H)
        Hexp += e

        num_clues = len(clues)
        if num_clues:
            # (x*2**e)**n = x**n * 2**(e*n).
            n = 1.0 / num_clues
            S = S**n * 2.0**(Sexp * n)
            H = H**n * 2.0**(Hexp * n)
            prob = S/(S+H)
        else:
            prob = 0.5

        if evidence:
            clues = [(w, p) for p, w, r in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            return prob, clues
        else:
            return prob

    if options.use_tim_combining:
        spamprob = tim_spamprob

    def chi2_spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import log as ln

        H = S = 0.0
        clues = self._getclues(wordstream)
        for prob, word, record in clues:
            if record is not None:  # else wordinfo doesn't know about it
                record.killcount += 1
            S += ln(1.0 - prob)
            H += ln(prob)

        n = len(clues)
        if n:
            S = 1.0 - chi2Q(-2.0 * S, 2*n)
            H = 1.0 - chi2Q(-2.0 * H, 2*n)
            prob = S/(S+H)
        else:
            prob = 0.5

        if evidence:
            clues = [(w, p) for p, w, r in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            clues.insert(0, ('*S*', S))
            clues.insert(0, ('*H*', H))
            return prob, clues
        else:
            return prob

    if options.use_chi_squared_combining:
        spamprob = chi2_spamprob

    def z_spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import sqrt

        clues = self._getclues(wordstream)
        zsum = 0.0
        for prob, word, record in clues:
            if record is not None:  # else wordinfo doesn't know about it
                record.killcount += 1
            zsum += normIP(prob)

        n = len(clues)
        if n:
            # We've added n zscores from a unit normal distribution.  By the
            # central limit theorem, their mean is normally distributed with
            # mean 0 and sdev 1/sqrt(n).  So the zscore of zsum/n is
            # (zsum/n - 0)/(1/sqrt(n)) = zsum/n/(1/sqrt(n)) = zsum/sqrt(n).
            prob = normP(zsum / sqrt(n))
        else:
            prob = 0.5

        if evidence:
            clues = [(w, p) for p, w, r in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            clues.insert(0, ('*zsum*', zsum))
            clues.insert(0, ('*n*', n))
            clues.insert(0, ('*zscore*', zsum / sqrt(n or 1)))
            return prob, clues
        else:
            return prob

    if options.use_z_combining:
        spamprob = z_spamprob

    def _add_popstats(self, sum, sumsq, n, is_spam):
        from math import ldexp

        if is_spam:
            sum += self.spamsum
            sumsq += self.spamsumsq
            n += self.spamn
            self.spamsum, self.spamsumsq, self.spamn = sum, sumsq, n
        else:
            sum += self.hamsum
            sumsq += self.hamsumsq
            n += self.hamn
            self.hamsum, self.hamsumsq, self.hamn = sum, sumsq, n

        mean = ldexp(sum, -64) / n
        var = sumsq * n - sum**2
        var = ldexp(var, -128) / n**2

        if is_spam:
            self.spammean, self.spamvar = mean, var
        else:
            self.hammean, self.hamvar = mean, var

    def central_limit_compute_population_stats(self, msgstream, is_spam):
        from math import ldexp

        sum = sumsq = 0
        seen = {}
        for msg in msgstream:
            for prob, word, record in self._getclues(msg):
                if word in seen:
                    continue
                seen[word] = 1
                prob = long(ldexp(prob, 64))
                sum += prob
                sumsq += prob * prob

        self._add_popstats(sum, sumsq, len(seen), is_spam)

    if options.use_central_limit:
        compute_population_stats = central_limit_compute_population_stats

    def central_limit_spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import sqrt

        clues = self._getclues(wordstream)
        sum = 0.0
        for prob, word, record in clues:
            sum += prob
            if record is not None:
                record.killcount += 1
        n = len(clues)
        if n == 0:
            return 0.5
        mean = sum / n

        # If this sample is drawn from the spam population, its mean is
        # distributed around spammean with variance spamvar/n.  Likewise
        # for if it's drawn from the ham population.  Compute a normalized
        # z-score (how many stddevs is it away from the population mean?)
        # against both populations, and then it's ham or spam depending
        # on which population it matches better.
        zham = (mean - self.hammean) / sqrt(self.hamvar / n)
        zspam = (mean - self.spammean) / sqrt(self.spamvar / n)
        delta = abs(zham) - abs(zspam)  # > 0 for spam, < 0 for ham

        azham, azspam = abs(zham), abs(zspam)
        if azham < azspam:
            ratio = azspam / max(azham, 1e-10) # guard against 0 division
        else:
            ratio = azham / max(azspam, 1e-10) # guard against 0 division
        certain = ratio > options.zscore_ratio_cutoff

        if certain:
            score = delta > 0.0 and 1.0 or 0.0
        else:
            score = delta > 0.0 and 0.51 or 0.49

        if evidence:
            clues = [(word, prob) for prob, word, record in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            extra = [('*zham*', zham),
                     ('*zspam*', zspam),
                     ('*hmean*', mean),
                     ('*smean*', mean),
                     ('*n*', n),
                    ]
            clues[0:0] = extra
            return score, clues
        else:
            return score

    if options.use_central_limit:
        spamprob = central_limit_spamprob

    def central_limit_compute_population_stats2(self, msgstream, is_spam):
        from math import ldexp, log

        sum = sumsq = 0
        seen = {}
        for msg in msgstream:
            for prob, word, record in self._getclues(msg):
                if word in seen:
                    continue
                seen[word] = 1
                if is_spam:
                    prob = log(prob)
                else:
                    prob = log(1.0 - prob)
                prob = long(ldexp(prob, 64))
                sum += prob
                sumsq += prob * prob

        self._add_popstats(sum, sumsq, len(seen), is_spam)

    if options.use_central_limit2:
        compute_population_stats = central_limit_compute_population_stats2

    def central_limit_spamprob2(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import sqrt, log

        clues = self._getclues(wordstream)
        hsum = ssum = 0.0
        for prob, word, record in clues:
            ssum += log(prob)
            hsum += log(1.0 - prob)
            if record is not None:
                record.killcount += 1
        n = len(clues)
        if n == 0:
            return 0.5
        hmean = hsum / n
        smean = ssum / n

        # If this sample is drawn from the spam population, its mean is
        # distributed around spammean with variance spamvar/n.  Likewise
        # for if it's drawn from the ham population.  Compute a normalized
        # z-score (how many stddevs is it away from the population mean?)
        # against both populations, and then it's ham or spam depending
        # on which population it matches better.
        zham = (hmean - self.hammean) / sqrt(self.hamvar / n)
        zspam = (smean - self.spammean) / sqrt(self.spamvar / n)
        delta = abs(zham) - abs(zspam)  # > 0 for spam, < 0 for ham

        azham, azspam = abs(zham), abs(zspam)
        if azham < azspam:
            ratio = azspam / max(azham, 1e-10) # guard against 0 division
        else:
            ratio = azham / max(azspam, 1e-10) # guard against 0 division
        certain = ratio > options.zscore_ratio_cutoff

        if certain:
            score = delta > 0.0 and 1.0 or 0.0
        else:
            score = delta > 0.0 and 0.51 or 0.49

        if evidence:
            clues = [(word, prob) for prob, word, record in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            extra = [('*zham*', zham),
                     ('*zspam*', zspam),
                     ('*hmean*', hmean),
                     ('*smean*', smean),
                     ('*n*', n),
                    ]
            clues[0:0] = extra
            return score, clues
        else:
            return score

    if options.use_central_limit2 or options.use_central_limit3:
        spamprob = central_limit_spamprob2

    def central_limit_compute_population_stats3(self, msgstream, is_spam):
        from math import ldexp, log

        sum = sumsq = n = 0
        for msg in msgstream:
            n += 1
            probsum = 0.0
            clues = self._getclues(msg)
            for prob, word, record in clues:
                if is_spam:
                    probsum += log(prob)
                else:
                    probsum += log(1.0 - prob)
            mean = long(ldexp(probsum / len(clues), 64))
            sum += mean
            sumsq += mean * mean

        self._add_popstats(sum, sumsq, n, is_spam)

    if options.use_central_limit3:
        compute_population_stats = central_limit_compute_population_stats3
