from __future__ import generators
# Dump every property we can find for a MAPI item

from win32com.client import Dispatch, constants
import pythoncom
import os, sys

from win32com.mapi import mapi, mapiutil
from win32com.mapi.mapitags import *

mapi.MAPIInitialize(None)
logonFlags = (mapi.MAPI_NO_MAIL |
              mapi.MAPI_EXTENDED |
              mapi.MAPI_USE_DEFAULT)
session = mapi.MAPILogonEx(0, None, None, logonFlags)

def GetMessageStores():
    tab = session.GetMsgStoresTable(0)
    rows = mapi.HrQueryAllRows(tab,
                               (PR_ENTRYID, PR_DISPLAY_NAME_A, PR_DEFAULT_STORE),   # columns to retrieve
                               None,     # all rows
                               None,            # any sort order is fine
                               0)               # any # of results is fine
    for row in rows:
        (eid_tag, eid), (name_tag, name), (def_store_tag, def_store) = row
        # Open the store.
        store = session.OpenMsgStore(
                            0,      # no parent window
                            eid,    # msg store to open
                            None,   # IID; accept default IMsgStore
                            # need write access to add score fields
                            mapi.MDB_WRITE |
                                # we won't send or receive email
                                mapi.MDB_NO_MAIL |
                                mapi.MAPI_DEFERRED_ERRORS)
        yield store, name, def_store

def _FindSubfolder(store, folder, find_name):
    find_name = find_name.lower()
    table = folder.GetHierarchyTable(0)
    rows = mapi.HrQueryAllRows(table, (PR_ENTRYID, PR_DISPLAY_NAME_A), None, None, 0)
    for (eid_tag, eid), (name_tag, name), in rows:
        if name.lower() == find_name:
            return store.OpenEntry(eid, None, mapi.MAPI_DEFERRED_ERRORS)
    return None

def FindFolder(name):
    assert name
    names = [n.lower() for n in name.split("\\")]
    if names[0]:
        for store, name, is_default in GetMessageStores():
            if is_default:
                store_name = name.lower()
                break
        folder_names = names
    else:
        store_name = names[1]
        folder_names = names[2:]
    # Find the store with the name
    for store, name, is_default in GetMessageStores():
        if name.lower() == store_name:
            folder_store = store
            break
    else:
        raise ValueError, "The store '%s' can not be located" % (store_name,)

    hr, data = store.GetProps((PR_IPM_SUBTREE_ENTRYID,), 0)
    subtree_eid = data[0][1]
    folder = folder_store.OpenEntry(subtree_eid, None, mapi.MAPI_DEFERRED_ERRORS)

    for name in folder_names:
        folder = _FindSubfolder(folder_store, folder, name)
        if folder is None:
            raise ValueError, "The subfolder '%s' can not be located" % (name,)
    return folder_store, folder        

# Also in new versions of mapituil
def GetAllProperties(obj, make_pretty = True):
    tags = obj.GetPropList(0)
    hr, data = obj.GetProps(tags)
    ret = []
    for tag, val in data:
        if make_pretty:
            hr, tags, array = obj.GetNamesFromIDs( (tag,) )
            if type(array[0][1])==type(u''):
                name = array[0][1]
            else:
                name = mapiutil.GetPropTagName(tag)
            # pretty value transformations
            if PROP_TYPE(tag)==PT_ERROR:
                val = mapiutil.GetScodeString(val)
        else:
            name = tag
        ret.append((name, val))
    return ret

def _FindItemsWithValue(folder, prop_tag, prop_val):
    tab = folder.GetContentsTable(0)
    # Restriction for the table:  get rows where our prop values match
    restriction = (mapi.RES_CONTENT,   # a property restriction
                   (mapi.FL_SUBSTRING | mapi.FL_IGNORECASE | mapi.FL_LOOSE, # fuzz level
                    prop_tag,   # of the given prop
                    (prop_tag, prop_val))) # with given val
    rows = mapi.HrQueryAllRows(tab,
                               (PR_ENTRYID,),   # columns to retrieve
                               restriction,     # only these rows
                               None,            # any sort order is fine
                               0)               # any # of results is fine
    # get entry IDs
    return [row[0][1] for row in rows]


def DumpItemProps(item, shorten):
    for prop_name, prop_val in GetAllProperties(item):
        prop_repr = repr(prop_val)
        if shorten:
            prop_repr = prop_repr[:50]
        print "%-20s: %s" % (prop_name, prop_repr)

def DumpProps(mapi_msgstore, mapi_folder, subject, include_attach, shorten):
    hr, data = mapi_folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
    name = data[0][1]
    eids = _FindItemsWithValue(mapi_folder, PR_SUBJECT_A, subject)
    print "Folder '%s' has %d items matching '%s'" % (name, len(eids), subject)
    for eid in eids:
        print "Dumping item with ID", mapi.HexFromBin(eid)
        item = mapi_msgstore.OpenEntry(eid,
                                       None,
                                       mapi.MAPI_DEFERRED_ERRORS)
        DumpItemProps(item, shorten)
        if include_attach:
            print
            table = item.GetAttachmentTable(0)
            rows = mapi.HrQueryAllRows(table, (PR_ATTACH_NUM,), None, None, 0)
            for row in rows:
                attach_num = row[0][1]
                print "Dumping attachment (PR_ATTACH_NUM=%d)" % (attach_num,)
                attach = item.OpenAttach(attach_num, None, mapi.MAPI_DEFERRED_ERRORS)
                DumpItemProps(attach, shorten)

def DumpTopLevelFolders():
    print "Top-level folder names are:"
    for store, name, is_default in GetMessageStores():
        # Find the folder with the content.
        hr, data = store.GetProps((PR_IPM_SUBTREE_ENTRYID,), 0)
        subtree_eid = data[0][1]
        folder = store.OpenEntry(subtree_eid, None, mapi.MAPI_DEFERRED_ERRORS)
        # Now the top-level folders in the store.
        table = folder.GetHierarchyTable(0)
        rows = mapi.HrQueryAllRows(table, (PR_DISPLAY_NAME_A), None, None, 0)
        for (name_tag, folder_name), in rows:
            print " \\%s\\%s" % (name, folder_name)

def usage():
    def_store_name = "<??unknown??>"
    for store, name, is_def in GetMessageStores():
        if is_def:
            def_store_name = name
    msg = """\
Usage: %s [-f foldername] subject of the message
-f - Search for the message in the specified folder (default = Inbox)
-s - Shorten long property values.
-a - Include attachments
-n - Show top-level folder names and exit

Dumps all properties for all messages that match the subject.  Subject
matching is substring and ignore-case.

Folder name must be a hierarchical 'path' name, using '\\'
as the path seperator.  If the folder name begins with a
\\, it must be a fully-qualified name, including the message
store name. For example, your Inbox can be specified either as:
  -f "Inbox"
or
  -f "\\%s\\Inbox"

Use the -n option to see all top-level folder names from all stores.
""" % (os.path.basename(sys.argv[0]), def_store_name)
    print msg


def main():
    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "af:sn")
    except getopt.error, e:
        print e
        print
        usage()
        sys.exit(1)
    folder_name = ""

    shorten = False
    include_attach = False
    for opt, opt_val in opts:
        if opt == "-f":
            folder_name = opt_val
        elif opt == "-s":
            shorten = True
        elif opt == "-a":
            include_attach = True
        elif opt == "-n":
            DumpTopLevelFolders()
            sys.exit(1)
        else:
            print "Invalid arg"
            return

    if not folder_name:
        folder_name = "Inbox" # Assume this exists!

    subject = " ".join(args)
    if not subject:
        print "You must specify a subject"
        print
        usage()
        sys.exit(1)

    try:
        store, folder = FindFolder(folder_name)
    except ValueError, details:
        print details
        sys.exit(1)

    DumpProps(store, folder, subject, include_attach, shorten)

if __name__=='__main__':
    main()
