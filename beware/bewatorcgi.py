import urllib
import httplib
import hashlib
from datetime import datetime, timedelta
from StringIO import StringIO

from reservations import reservation

class BewatorCgi:
    def __init__(self, hostname):
        self.hostname = hostname
        
        self.conn = httplib.HTTPConnection(hostname)
    
    def __skipDelimiter(self, f):
        d = f.read(1)
        if d != '\t':
            raise Exception("parse error because " + str(ord(d)))

    def __readByteParam(self, f):
        s = f.read(2)
    
        assert s[0] == '1' or s[0] == '0'
    
        if s[0] == '1':
            return ord(s[1]) - ord('0')
    
        return ord(s[1])

    def __readByteParamArray(self, f, n):
            i = 0

            a = []
        
            while i < n:
                i += 1
                a.append(self.__readByteParam(f))
        
            return a
    
    def __readShortByteParam(self, f):
        return self.__readByteParam(f) << 8 | self.__readByteParam(f)
    
    def __testBit(self, array, i):
        return (array[i / 8] & 1 << i % 8) != 0
    
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
    
    def getBookingObjects(self, session):
        self.conn.request("GET", "/names.cgi?session=%d" % session)
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
            raise Exception("Response: " + str(ord(r)))
        
        of.read(1)
        
        objects = []

        i = 1
        
        while of.read(1) == '1':
            l = int(of.read(1))
        
            self.__skipDelimiter(of)
        
            ostr = of.read(l).decode('iso-8859-1')
            objects.append((i, ostr))
            of.read(1)
            i += 1
        
        return objects

    def getTime(self, sessionId, obj):
        self.conn.request("GET", "/time.cgi?session=%d&object=%d" % (sessionId, obj))
        r = self.conn.getresponse()
    
        buf = r.read()
        f = StringIO(buf)
        s = f.read()
    
        s = s.split('\t')
    
        stamp = int(s[5])
        
        return (stamp, int(s[4][1]))

    def getReservations(self, session, obj, fromTime):
        """Get an object holding the reservations starting at time fromTime.
           That time is the Bewator 'seconds' since 1990 timestamp.""" 
        
        self.conn.request("GET", "/combo.cgi?session=%d&object=%d&start=%d&stop=%d" % (session, obj, fromTime/86400, fromTime/86400+6))
        
        r = self.conn.getresponse()
    
        resstr = r.read()
    
        f = StringIO(resstr)
        f.read(1)
    
        status = ord(f.read(1))

        if status != 48:
            return (status, None)
    
        self.__skipDelimiter(f)
    
        nintervals = self.__readByteParam(f)
    
        intervals = []
        i = 0
        while i < nintervals:
            self.__skipDelimiter(f)
            i0 = int(f.read(5))
            self.__skipDelimiter(f)
            i1 = int(f.read(5))
    
            intervals.append((i0, i1))
    
            i += 1

        # weekdays
        weekday_timeslice_bitmap = []
        i = 0
        while i < 7:
            i += 1
            self.__skipDelimiter(f)
            weekday_timeslice_bitmap.append(self.__readByteParamArray(f, 3))
    
        self.__skipDelimiter(f)
    
        forward_booking_time = self.__readShortByteParam(f)
    
        self.__skipDelimiter(f)
    
        num_of_reddays = self.__readByteParam(f)
    
        i = 0
        reddays = []
        while i < num_of_reddays:
            i += 1
            self.__skipDelimiter(f)
            reddays.append(self.__readShortByteParam(f))
    
        num_of_holidays = self.__readByteParam(f)
    
        holidays = []
        i = 0
        while i < num_of_holidays:
            i += 1
            self.__skipDelimiter(f)
            holidays.append((self.__readShortByteParam(f), self.__readShortByteParam(f)))
    
        self.__skipDelimiter(f)
    
        min_time_rem = int(f.read(5))
    
        self.__skipDelimiter(f)
    
        flexible_ts = self.__readByteParam(f) == 1
    
        if flexible_ts:
            raise Exception("Unable to handle flexible_ts option")
    
        tintervals = nintervals * 7
        k = tintervals / 8
        if tintervals % 8 > 0:
            k += 1
    
        assert f.read(1) == '0'
    
        self.__skipDelimiter(f)
        otherBookings = self.__readByteParamArray(f, k)
    
        self.__skipDelimiter(f)
        myBookings = self.__readByteParamArray(f, k)
    
        bookings = []
    
        i = 0
        
        dt = (datetime(1990, 1, 1, 0, 0) + timedelta(seconds = fromTime)).replace(hour = 0, minute = 0, second = 0)
        
        while i < tintervals:
    
            if self.__testBit(myBookings, i):
                b = 2
            elif self.__testBit(otherBookings, i):
                b = 1
            else:
                b = 0

            ddt = dt + timedelta(days = i/k)

            startOfDay = (ddt - datetime(1990, 1, 1, 0, 0)).total_seconds()
        
            interval = intervals[i % len(intervals)]
    
            tsFrom = startOfDay + interval[0]
            tsTo = startOfDay + interval[1]
            
            r = reservation(obj, tsFrom, tsTo, b)
    
            bookings.append(r)
    
            i += 1
    
        self.__skipDelimiter(f)
        serviceStart = int(f.read(10))
        self.__skipDelimiter(f)
        serviceStop = int(f.read(10))
    
        return (status, bookings)

    def makeReservation(self, session, obj, start, end):
        self.conn.request("GET", "/makeres.cgi?session=%d&object=%d&start=%d&stop=%d" % (session, obj, start, end))
        r = self.conn.getresponse()
    
        resstr = r.read()
    
        f = StringIO(resstr)
        f.read(1)
    
        status = f.read(1)

        return ord(status)
    
    def cancelReservation(self, session, obj, start):
        self.conn.request("GET", "/cancelres.cgi?session=%d&object=%d&start=%d" % (session, obj, start))
        r = self.conn.getresponse()
    
        resstr = r.read()
    
        f = StringIO(resstr)
        f.read(1)
    
        status = f.read(1)

        return ord(status)
