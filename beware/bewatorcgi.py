import urllib
import httplib
import hashlib
from StringIO import StringIO

class BewatorCgi:
    def __init__(self, hostname):
        self.hostname = hostname
        
        self.conn = httplib.HTTPConnection(hostname)
    
    def __skipDelimiter(self, f):
        d = f.read(1)
        if d != '\t':
            raise Exception("parse error because " + str(ord(d)))

    
    def login(self, user, password):
        passhash = hashlib.md5(password).hexdigest()
        
        self.conn.request("GET", "/login.cgi?id=%s&data=%s&type=1" % (user, passhash))
        r = self.conn.getresponse()
        
        if r.status != 200:
            return -1
        
        s = r.read()
        
        status = ord(s[1])
        
        # FIXME parse and return something useful
        if status != 48 or len(s) < 4:
            return -1
        
        sessid = ord(s[3]) - 48
        
        return sessid
    
    def listObjects(self, session):
        self.conn.request("GET", "/names.cgi?session=%s" % session)
        r = self.conn.getresponse()
        
        if r.status != 200:
            raise Exception("" + str(r.status))

        buf = r.read()
        
        f = StringIO(buf)
        
        s = f.read()
        
        of = StringIO(s)
        
        of.read(1)
        r = of.read(1)
        if r != '0':
            print "nok response for object fetch"
            raise Exception("Response: " + str(ord(r)))
        
        of.read(1)
        
        objects = []

        #
        i = 1
        
        while of.read(1) == '1':
            l = int(of.read(1))
        
            self.__skipDelimiter(of)
        
            ostr = of.read(l).decode('iso-8859-1')
            print "Got object:", ostr
            objects.append((i, ostr))
            of.read(1)
            i += 1
        
        return objects