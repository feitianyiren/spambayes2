# Exports your ham and spam folders to a standard SpamBayes test directory

import sys, os, shutil
from manager import GetManager


def BuildBuckets(manager, root_directory, folder_ids, include_sub):
    store = manager.message_store
    config = manager.config
    num = 0
    for folder in store.GetFolderGenerator(config.training.spam_folder_ids, config.training.spam_include_sub):
        for msg in folder.GetMessageGenerator():
            num += 1
    num_buckets = num / 400
    dirs = []
    for i in range(num_buckets):
        dir=os.path.join(root_directory, "Set%d" % (i+1,))
        dir=os.path.abspath(dir)
        if os.path.isdir(dir):
            shutil.rmtree(dir)
        os.makedirs(dir)
        dirs.append(dir)
    return dirs

def ChooseBucket(buckets):
    import random
    return random.choice(buckets)

def _export_folders(manager, dir, folder_ids, include_sub):
    num = 0
    store = manager.message_store
    buckets = BuildBuckets(manager, dir, folder_ids, include_sub)
    for folder in store.GetFolderGenerator(folder_ids, include_sub):
        print "", folder.name
        for message in folder.GetMessageGenerator():
            dir = ChooseBucket(buckets)
            # filename is the EID.txt
            try:
                msg_text = str(message.GetEmailPackageObject())
            except KeyboardInterrupt:
                raise
            except:
                print "Failed to get message text for '%s': %s" \
                      % (message.GetSubject(), sys.exc_info()[1])
                continue

            fname = os.path.join(dir, message.GetID()[1]) + ".txt"
            f = open(fname, "w")
            f.write(msg_text)
            f.close()
            num += 1
    return num

def export(directory):
    print "Loading bayes manager..."
    manager = GetManager()
    config = manager.config

    print "Exporting spam..."
    num = _export_folders(manager, os.path.join(directory, "Spam"),
                          config.training.spam_folder_ids, config.training.spam_include_sub)
    print "Exported", num, " spam messages."

    print "Exporting ham...",
    num = _export_folders(manager, os.path.join(directory, "Ham"),
                          config.training.ham_folder_ids, config.training.ham_include_sub)
    print "Exported", num, " ham messages."

def main():
    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "q")
    except getopt.error, d:
        print d
        print
        usage()
    quiet = 0
    for opt, val in opts:
        if opt=='-q':
            quiet = 1

    if len(args) > 1:
        print "Only one directory name can be specified"
        print
        usage()

    if len(args)==0:
        directory = os.path.join(os.path.dirname(sys.argv[0]), "..\\Data")
    else:
        directory = args[0]

    directory = os.path.abspath(directory)
    print "This program will export your Outlook Ham and Spam folders"
    print "to the directory '%s'" % (directory,)
    if os.path.exists(directory):
        print "*******"
        print "WARNING: all existing files in '%s' will be deleted" % (directory,)
        print "*******"
    if not quiet:
        raw_input("Press enter to continue, or Ctrl+C to abort.")
    export(directory)

def usage():
    print """ \
Usage: %s -q [directory]

-q : quiet - don't prompt for confirmation.

Export the folders defined in the Outlook Plugin to a test directory.
The directory structure is as defined in the parent README.txt file,
in the "Standard Test Data Setup" section.

If 'directory' is not specified, '..\\Data' is assumed.

If 'directory' exists, it will be recursively deleted before
the export (but you will be asked to confirm unless -q is given).""" \
            % (os.path.basename(sys.argv[0]))
    sys.exit(1)

if __name__=='__main__':
    main()
