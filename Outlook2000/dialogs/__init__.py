# This package defines dialog boxes used by the main
# SpamBayes Outlook 2k integration code.

def LoadDialogs(rc_file = "dialogs.rc"):
    import os
    from resources import rcparser
    if not os.path.isabs(rc_file):
        rc_file = os.path.join( os.path.dirname( rcparser.__file__ ), rc_file)
    return rcparser.ParseDialogs(rc_file)

def ShowDialog(parent, manager, idd):
    """Displays another dialog"""
    if manager.dialog_parser is None:
        manager.dialog_parser = LoadDialogs()
    import dialog_map
    commands = dialog_map.dialog_map[idd]
    if not parent:
        import win32gui
        try:
            parent = win32gui.GetActiveWindow()
        except win32gui.error:
            pass
        
    import dlgcore
    dlg = dlgcore.ProcessorDialog(parent, manager, idd, commands)
    dlg.DoModal()
    
import dlgutils
SetWaitCursor = dlgutils.SetWaitCursor
