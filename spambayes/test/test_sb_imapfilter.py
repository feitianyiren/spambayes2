# Test sb_imapfilter script.

import sys
import time
import types
import socket
import thread
import imaplib
import unittest
import asyncore

import sb_test_support
sb_test_support.fix_sys_path()

from spambayes import Dibbler
from spambayes.Options import options
from sb_imapfilter import BadIMAPResponseError
from sb_imapfilter import IMAPSession, IMAPMessage, IMAPFolder

IMAP_PORT = 8143
IMAP_USERNAME = "testu"
IMAP_PASSWORD = "testp"
IMAP_FOLDER_LIST = ["INBOX", "unsure", "ham_to_train", "spam"]
# Key is UID.
IMAP_MESSAGES = {101 : """Subject: Test\r\n\r\nBody test.""",
                 102 : """Subject: Test2\r\n\r\nAnother body test.""",
                 # 103 is taken from Anthony's email torture test
                 # (the test_zero-length-boundary file).
                 103 : """Received: from noisy-2-82-67-182-141.fbx.proxad.net(82.67.182.141)
 via SMTP by mx1.example.com, id smtpdAAAzMayUR; Tue Apr 27 18:56:48 2004
Return-Path: " Freeman" <XLUPSYGSHLBAPN@runbox.com>
Received: from  rly-xn05.mx.aol.com (rly-xn05.mail.aol.com [172.20.83.138]) by air-xn02.mail.aol.com (v98.10) with ESMTP id MAILINXN22-6504043449c151; Tue, 27 Apr 2004 16:57:46 -0300
Received: from 132.16.224.107 by 82.67.182.141; Tue, 27 Apr 2004 14:54:46 -0500
From: " Gilliam" <.@doramail.com>
To: To: user@example.com
Subject: Your Source For Online Prescriptions....Soma-Watson..VALIUM-Roche    .		
Date: Wed, 28 Apr 2004 00:52:46 +0500
Mime-Version: 1.0
Content-Type: multipart/alternative;
        boundary=""
X-Mailer: AOL 7.0 for Windows US sub 118
X-AOL-IP: 114.204.176.98
X-AOL-SCOLL-SCORE: 1:XXX:XX
X-AOL-SCOLL-URL_COUNT: 2
Message-ID: <@XLUPSYGSHLBAPN@runbox.com>

--
Content-Type: text/html;
        charset="iso-8859-1"
Content-Transfer-Encoding: quoted-printable

<strong><a href=3D"http://www.ibshels454drugs.biz/c39/">ENTER HERE</a> to
ORDER MEDS Online, such as XANAX..VALIUM..SOMA..Much MORE SHIPPED
OVERNIGHT,to US and INTERNATIONAL</strong>

---

""",
                 }
# Map of ID -> UID
IMAP_UIDS = {1 : 101, 2: 102, 3:103}

class TestListener(Dibbler.Listener):
    """Listener for TestIMAP4Server.  Works on port 8143, to co-exist
    with real IMAP4 servers."""
    def __init__(self, socketMap=asyncore.socket_map):
        Dibbler.Listener.__init__(self, IMAP_PORT, TestIMAP4Server,
                                  (socketMap,), socketMap=socketMap)


# If true, the next command will fail, whatever it is.
FAIL_NEXT = False
class TestIMAP4Server(Dibbler.BrighterAsyncChat):
    """Minimal IMAP4 server, for testing purposes.  Accepts a limited
    subset of commands, and also a KILL command, to terminate."""
    def __init__(self, clientSocket, socketMap):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        Dibbler.BrighterAsyncChat.__init__(self)
        Dibbler.BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.set_terminator('\r\n')
        # okCommands are just ignored (we pass back a happy this-was-fine
        # answer, and do nothing.
        self.okCommands = ['NOOP', 'LOGOUT', 'CAPABILITY', 'KILL']
        # These commands actually result in something.
        self.handlers = {'LIST' : self.onList,
                         'LOGIN' : self.onLogin,
                         'SELECT' : self.onSelect,
                         'FETCH' : self.onFetch,
                         'UID' : self.onUID,
                         }
        self.push("* OK [CAPABILITY IMAP4REV1 AUTH=LOGIN] " \
                  "localhost IMAP4rev1\r\n")
        self.request = ''

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override."""
        global FAIL_NEXT
        id, command = self.request.split(None, 1)

        if FAIL_NEXT:
            FAIL_NEXT = False
            self.push("%s NO Was told to fail.\r\n" % (id,))

        if ' ' in command:
            command, args = command.split(None, 1)
        else:
            args = ''
        command = command.upper()
        if command in self.okCommands:
            self.push("%s OK (we hope)\r\n" % (id,))
            if command == 'LOGOUT':
                self.close_when_done()
            if command == 'KILL':
                self.socket.shutdown(2)
                self.close()
                raise SystemExit()
        else:
            handler = self.handlers.get(command, self.onUnknown)
            self.push(handler(id, command, args, False))  # Or push_slowly for testing
        self.request = ''

    def push_slowly(self, response):
        """Useful for testing."""
        for c in response:
            self.push(c)
            time.sleep(0.02)

    def onLogin(self, id, command, args, uid=False):
        """Log in to server."""
        username, password = args.split(None, 1)
        username = username.strip('"')
        password = password.strip('"')
        if username == IMAP_USERNAME and password == IMAP_PASSWORD:
            return "%s OK [CAPABILITY IMAP4REV1] User %s " \
                   "authenticated.\r\n" % (id, username)
        return "%s NO LOGIN failed\r\n" % (id,)

    def onList(self, id, command, args, uid=False):
        """Return list of folders."""
        base = '\r\n* LIST (\\NoInferiors \\UnMarked) "/" '
        return "%s%s\r\n%s OK LIST completed\r\n" % \
               (base[2:], base.join(IMAP_FOLDER_LIST), id)

    def onSelect(self, id, command, args, uid=False):
        exists = "* %d EXISTS" % (len(IMAP_MESSAGES),)
        recent = "* 0 RECENT"
        uidv = "* OK [UIDVALIDITY 1091599302] UID validity status"
        next_uid = "* OK [UIDNEXT 23] Predicted next UID"
        flags = "* FLAGS (\Answered \Flagged \Deleted \Draft \Seen)"
        perm_flags = "* OK [PERMANENTFLAGS (\* \Answered \Flagged " \
                     "\Deleted \Draft \Seen)] Permanent flags"
        complete = "%s OK [READ-WRITE] SELECT completed" % (id,)
        return "%s\r\n" % ("\r\n".join([exists, recent, uidv, next_uid,
                                        flags, perm_flags, complete]),)

    def onFetch(self, id, command, args, uid=False):
        msg_nums, msg_parts = args.split(None, 1)
        msg_nums = msg_nums.split()
        response = {}
        for msg in msg_nums:
            response[msg] = []
        if "UID" in msg_parts:
            if uid:
                for msg in msg_nums:
                    response[msg].append("FETCH (UID %s)" % (msg,))
            else:
                for msg in msg_nums:
                    response[msg].append("FETCH (UID %s)" %
                                         (IMAP_UIDS[int(msg)]))
        if "BODY.PEEK[]" in msg_parts:
            for msg in msg_nums:
                if uid:
                    msg_uid = int(msg)
                else:
                    msg_uid = IMAP_UIDS[int(msg)]
                response[msg].append(("FETCH (BODY[] {%s}" %
                                     (len(IMAP_MESSAGES[msg_uid])),
                                     IMAP_MESSAGES[msg_uid]))
        for msg in msg_nums:
            try:
                simple = " ".join(response[msg])
            except TypeError:
                simple = []
                for part in response[msg]:
                    if isinstance(part, types.StringTypes):
                        simple.append(part)
                    else:
                        simple.append('%s\r\n%s)' % (part[0], part[1]))
                simple = " ".join(simple)
            response[msg] = "* %s %s" % (msg, simple)
        response_text = "\r\n".join(response.values())
        return "%s\r\n%s OK FETCH completed\r\n" % (response_text, id)

    def onUID(self, id, command, args, uid=False):
        actual_command, args = args.split(None, 1)
        handler = self.handlers.get(actual_command, self.onUnknown)
        return handler(id, command, args, uid=True)

    def onUnknown(self, id, command, args, uid=False):
        """Unknown IMAP4 command."""
        return "%s BAD Command unrecognised: %s\r\n" % (id, repr(command))


class BaseIMAPFilterTest(unittest.TestCase):
    def setUp(self):
        self.imap = IMAPSession("localhost", IMAP_PORT)

    def tearDown(self):
        try:
            self.imap.logout()
        except imaplib.error:
            pass


class IMAPSessionTest(BaseIMAPFilterTest):
    def testConnection(self):
        # Connection is made in setup, just need to check
        # that it worked.
        self.assert_(self.imap.connected)
        
    def testGoodLogin(self):
        self.imap.login(IMAP_USERNAME, IMAP_PASSWORD)
        self.assert_(self.imap.logged_in)

    def testBadLogin(self):
        print "\nYou should see a message indicating that login failed."
        self.assertRaises(SystemExit, self.imap.login, IMAP_USERNAME,
                          "wrong password")

    def test_check_response(self):
        test_data = "IMAP response data"
        response = ("OK", test_data)
        data = self.imap.check_response("", response)
        self.assertEqual(data, test_data)
        response = ("NO", test_data)
        self.assertRaises(BadIMAPResponseError, self.imap.check_response,
                          "", response)

    def testSelectFolder(self):
        # This test will fail if testGoodLogin fails.
        self.imap.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        # Check handling of Python (not SpamBayes) bug #845560.
        self.assertRaises(BadIMAPResponseError, self.imap.SelectFolder, "")

        # Check selection.
        self.imap.SelectFolder("Inbox")
        response = self.imap.response('OK')
        self.assertEquals(response[0], "OK")
        self.assert_(response[1] != [None])

        # Check that we don't reselect if we are already in that folder.
        self.imap.SelectFolder("Inbox")
        response = self.imap.response('OK')
        self.assertEquals(response[0], "OK")
        self.assertEquals(response[1], [None])

    def test_folder_list(self):
        global FAIL_NEXT

        # This test will fail if testGoodLogin fails.
        self.imap.login(IMAP_USERNAME, IMAP_PASSWORD)

        # Everything working.        
        folders = self.imap.folder_list()
        correct = IMAP_FOLDER_LIST[:]
        correct.sort()
        self.assertEqual(folders, correct)

        # Bad command.
        print "\nYou should see a message indicating that getting the " \
              "folder list failed."
        FAIL_NEXT = True
        self.assertEqual(self.imap.folder_list(), [])

        # Literals in response.
        # XXX TO DO!
        
    def test_extract_fetch_data(self):
        response = "bad response"
        self.assertRaises(BadIMAPResponseError,
                          self.imap.extract_fetch_data, response)

        # Check UID and message_number.
        message_number = "123"
        uid = "5432"
        response = "%s (UID %s)" % (message_number, uid)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["message_number"], message_number)
        self.assertEqual(data["UID"], uid)

        # Check INTERNALDATE, FLAGS.
        flags = r"(\Seen \Deleted)"
        date = '"27-Jul-2004 13:11:56 +1200"'
        response = "%s (FLAGS %s INTERNALDATE %s)" % \
                   (message_number, flags, date)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["FLAGS"], flags)
        self.assertEqual(data["INTERNALDATE"], date)

        # Check RFC822 and literals.
        rfc = "Subject: Test\r\n\r\nThis is a test message."
        response = ("%s (RFC822 {%s}" % (message_number, len(rfc)), rfc)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["message_number"], message_number)
        self.assertEqual(data["RFC822"], rfc)

        # Check RFC822.HEADER.
        headers = "Subject: Foo\r\nX-SpamBayes-ID: 1231-1\r\n"
        response = ("%s (RFC822.HEADER {%s}" % (message_number,
                                                len(headers)), headers)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["RFC822.HEADER"], headers)

        # Check BODY.PEEK.
        peek = "Subject: Test2\r\n\r\nThis is another test message."
        response = ("%s (BODY[] {%s}" % (message_number, len(peek)),
                    peek)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["BODY[]"], peek)


class IMAPMessageTest(BaseIMAPFilterTest):
    def setUp(self):
        BaseIMAPFilterTest.setUp(self)
        self.msg = IMAPMessage()
        self.msg.imap_server = self.imap

    # These tests might fail if more than one second passes
    # between the call and the assert.  We could make it more robust,
    # or you could just run this on a faster machine, like me <wink>.
    def test_extract_time_no_date(self):
        date = self.msg.extractTime()
        self.assertEqual(date, imaplib.Time2Internaldate(time.time()))
    def test_extract_time_date(self):
        self.msg["Date"] = "Wed, 19 May 2004 20:05:15 +1200"
        date = self.msg.extractTime()
        self.assertEqual(date, '"19-May-2004 20:05:15 +1200"')
    def test_extract_time_bad_date(self):
        self.msg["Date"] = "Mon, 06 May 0102 10:51:16 -0100"
        date = self.msg.extractTime()
        self.assertEqual(date, imaplib.Time2Internaldate(time.time()))

    def test_as_string_invalid(self):
        content = "This is example content.\nThis is more\r\n"
        self.msg.invalid = True
        self.msg.invalid_content = content
        as_string = self.msg.as_string()
        self.assertEqual(self.msg._force_CRLF(content), as_string)

    def testMoveTo(self):
        fol1 = "Folder1"
        fol2 = "Folder2"
        self.msg.MoveTo(fol1)
        self.assertEqual(self.msg.folder, fol1)
        self.msg.MoveTo(fol2)
        self.assertEqual(self.msg.previous_folder, fol1)
        self.assertEqual(self.msg.folder, fol2)

    def test_get_full_message(self):
        self.assertRaises(AssertionError, self.msg.get_full_message)
        self.msg.id = "unittest"
        self.assertRaises(AttributeError, self.msg.get_full_message)

        self.msg.imap_server.login(IMAP_USERNAME, IMAP_PASSWORD)
        self.msg.imap_server.select()
        response = self.msg.imap_server.fetch(1, "UID")
        self.assertEqual(response[0], "OK")
        self.msg.uid = response[1][0][7:-1]
        self.msg.folder = IMAPFolder("Inbox", self.msg.imap_server)

        new_msg = self.msg.get_full_message()
        self.assertEqual(new_msg.folder, self.msg.folder)
        self.assertEqual(new_msg.previous_folder, self.msg.previous_folder)
        self.assertEqual(new_msg.uid, self.msg.uid)
        self.assertEqual(new_msg.id, self.msg.id)
        self.assertEqual(new_msg.rfc822_key, self.msg.rfc822_key)
        self.assertEqual(new_msg.rfc822_command, self.msg.rfc822_command)
        self.assertEqual(new_msg.imap_server, self.msg.imap_server)
        id_header = options["Headers", "mailid_header_name"]
        self.assertEqual(new_msg[id_header], self.msg.id)

        new_msg2 = new_msg.get_full_message()
        # These should be the same object, not just equal.
        self.assert_(new_msg is new_msg2)

    def test_get_bad_message(self):
        self.msg.id = "unittest"
        self.msg.imap_server.login(IMAP_USERNAME, IMAP_PASSWORD)
        self.msg.imap_server.select()
        self.msg.uid = 103 # id of malformed message in dummy server
        self.msg.folder = IMAPFolder("Inbox", self.msg.imap_server)
        print "\nWith email package versions less than 3.0, you should " \
              "see an error parsing the message."
        new_msg = self.msg.get_full_message()
        # With Python < 2.4 (i.e. email < 3.0) we get an exception
        # header.  With more recent versions, we get a defects attribute.
        # XXX I can't find a message that generates a defect!  Until
        # message 103 is replaced with one that does, this will fail with
        # Python 2.4/email 3.0.
        has_header = "X-Spambayes-Exception: " in new_msg.as_string()
        has_defect = hasattr(new_msg, "defects") and len(new_msg.defects) > 0
        self.assert_(has_header or has_defect)

    def test_get_memory_error_message(self):
        # XXX Figure out a way to trigger a memory error - but not in
        # the fake IMAP server, in imaplib, or our IMAP class.
        pass

    def test_Save(self):
        # XXX To-do
        pass


class IMAPFolderTest(BaseIMAPFilterTest):
    def setUp(self):
        BaseIMAPFilterTest.setUp(self)
        self.folder = IMAPFolder("testfolder", self.imap)

    def test_cmp(self):
        folder2 = IMAPFolder("testfolder", self.imap)
        folder3 = IMAPFolder("testfolder2", self.imap)
        self.assertEqual(self.folder, folder2)
        self.assertNotEqual(self.folder, folder3)
        
    def test_iter(self):
        # XXX To-do
        pass
    def test_keys(self):
        # XXX To-do
        pass
    def test_getitem(self):
        # XXX To-do
        pass

    def test_generate_id(self):
        print "\nThis test takes slightly over a second."
        id1 = self.folder._generate_id()
        id2 = self.folder._generate_id()
        id3 = self.folder._generate_id()
        # Need to wait at least one clock tick.
        time.sleep(1)
        id4 = self.folder._generate_id()
        self.assertEqual(id2, id1 + "-2")
        self.assertEqual(id3, id1 + "-3")
        self.assertNotEqual(id1, id4)
        self.assertNotEqual(id2, id4)
        self.assertNotEqual(id3, id4)
        self.assert_('-' not in id4)
        
    def test_Train(self):
        # XXX To-do
        pass
    def test_Filter(self):
        # XXX To-do
        pass


class IMAPFilterTest(BaseIMAPFilterTest):
    def test_Train(self):
        # XXX To-do
        pass
    def test_Filter(self):
        # XXX To-do
        pass


def suite():
    suite = unittest.TestSuite()
    for cls in (IMAPSessionTest,
                IMAPMessageTest,
                IMAPFolderTest,
                IMAPFilterTest,
               ):
        suite.addTest(unittest.makeSuite(cls))
    return suite

if __name__=='__main__':
    def runTestServer():
        TestListener()
        asyncore.loop()
    thread.start_new_thread(runTestServer, ())
    sb_test_support.unittest_main(argv=sys.argv + ['suite'])
