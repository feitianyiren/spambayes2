# configuration stuff we persist via a pickle
# Can't be defined in any module that may be used as "__main__"
# or as a module.

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


class _ConfigurationContainer:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __setattr__(self, attr, val):
        if not self.__dict__.has_key(attr):
            raise AttributeError, attr
        self.__dict__[attr] = val
    # Crap state-loading code so when we load an early version of the pickle
    # any attributes in the new version are considered defaults.
    # XXX - I really really want a better scheme than pickles etc here :(
    def _update_from(self, dict):
        for name, val in dict.items():
            updater = getattr(val, "_update_from", None)
            if updater is not None and self.__dict__.has_key(name):
                self.__dict__[name]._update_from(val.__dict__)
            else:
                self.__dict__[name] = val

    def __setstate__(self, state):
        self.__init__() # ensure any new/default values setup
        self._update_from(state)

    def _dump(self, thisname="<root>", level=0):
        import pprint
        prefix = "  " * level
        print "%s%s:" % (prefix, thisname)
        for name, ob in self.__dict__.items():
            d = getattr(ob, "_dump", None)
            if d is None:
                print "%s %s: %s" % (prefix, name, pprint.pformat(ob))
            else:
                d(name, level+1)

class ConfigurationRoot(_ConfigurationContainer):
    def __init__(self):
        training = _ConfigurationContainer(
            ham_folder_ids = [],
            ham_include_sub = False,
            spam_folder_ids = [],
            spam_include_sub = False,
            # Train as unsure/spam is moved back to Inbox
            train_recovered_spam = True,
            # Train as stuff dragged into spam folders.
            train_manual_spam = True,
            )
        filter = _ConfigurationContainer(
            watch_folder_ids = [],
            watch_include_sub = False,
            spam_folder_id = None,
            spam_threshold = 90,
            spam_action = "Untouched",
            unsure_folder_id = None,
            unsure_threshold = 15,
            unsure_action = "Untouched",
            enabled = False,
            )
        filter_now = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            only_unread = False,
            only_unseen = True,
            action_all = True,
            )
        field_score_name = "Spam"
        _ConfigurationContainer.__init__(self,
                                         training=training,
                                         filter=filter,
                                         filter_now = filter_now,
                                         field_score_name = field_score_name)

if __name__=='__main__':
    print "Please run 'manager.py'"
