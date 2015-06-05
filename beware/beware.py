# -*- coding: utf-8 -*-
from __future__ import print_function

from twisted.internet import reactor
from twisted.web import static, server, html
from twisted.web.resource import Resource
from datetime import datetime, timedelta
from twisted.web.util import redirectTo

import traceback

from bewatorcgi import BewatorCgi

# Templating
from jinja2 import Environment, PackageLoader

from urllib import quote
from calendar import calendar

URL = "localhost"

env = Environment(loader=PackageLoader('beware', 'templates'))

weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

siteRenderArgs = {'weekdays' : weekdays}

def badRequest(request, errorText):
    template = env.get_template("error.html")
    request.setResponseCode(400)
    return template.render(siteRenderArgs, error=errorText).encode("utf-8")

def bewatorRequestError(request, errorText):
    request.setResponseCode(418) # I'm a teapot!
    return str(errorText)

def getRoot(request):
    port = request.getHost().port
    if request.isSecure():
        default = 443
    else:
        default = 80
    if port == default:
        hostport = ''
    else:
        hostport = ':%d' % port
    prefix = 'http%s://%s%s/' % (request.isSecure() and 's' or '', request.getRequestHostname(), hostport)
    path = b'/'.join([quote(segment, safe=b'') for segment in request.prepath[:-1]])
    return prefix + path

def relogin(request):
    request.setResponseCode(401)
    return "Please login again"
    
def sessionExpired(request):
    return toUrl("?error=Session%20expired,%20please%20login%20again.", request)

def toUrl(url, request):
    getRoot(request)
    return redirectTo(getRoot(request) + url, request)
    

class Index(Resource):
    def getChild(self, name, request):
        if name == '':
            return self
        return Resource.getChild(self, name, request)
    
    def render_GET(self, request):
        template = env.get_template('index.html')
        
        error = None
        
        if "error" in request.args:
            error = html.escape(request.args["error"][0])
        
        return template.render(siteRenderArgs, error=error).encode("utf-8")

class Login(Resource):
    def render_POST(self, request):
        if not "user" in request.args or not "password" in request.args:
            return badRequest(request, "Please don't call me without the proper parameters!")
        
        user = request.args["user"][0]
        password = request.args["password"][0]
        
        session = request.getSession()
        session.bcgi = BewatorCgi(URL)
        sessionId = session.bcgi.login(html.escape(user), password)
        
        if sessionId < 0:
            print("Login failed for user " + user + " from " + str(request.getClientIP()))
            return toUrl("?error=Login%20failed", request)
        
        print("Login successful for user " + user + " from " + str(request.getClientIP()))
        
        session.bewator_session = int(sessionId)
        
        return toUrl("objects", request)

class ListObjects(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return sessionExpired(request)
        
        try:
            objects = session.bcgi.getBookingObjects(session.bewator_session)
        except Exception:
            # Assume logged out if exception is thrown, log the exception and relogin user.
            print('-'*60)
            traceback.print_exc(file=sys.stdout)
            print('-'*60)

            return relogin(request)
        
        template = env.get_template("objects.html")
        return template.render(siteRenderArgs, objects=objects).encode("utf-8")

class ListReservations(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return relogin(request)

        if not "object" in request.args:
            return badRequest(request, "no object specified")

        obj = request.args["object"][0]

        if not obj.isdigit():
            return badRequest(request, "nasty-error!")
        
        obj = int(obj)

        dt = datetime.now()
        
        # for mondays..
        dt -= timedelta(days = dt.weekday(), seconds=dt.second, hours=dt.hour, minutes = dt.minute, microseconds = dt.microsecond)
        
        startTime = int((dt - datetime(1990, 1, 1, 0, 0)).total_seconds())
        nowTime = int((datetime.now() - datetime(1990, 1, 1, 0, 0)).total_seconds())

        if "fromTs" in request.args and request.args["fromTs"][0].isdigit():
            myTime = int(request.args["fromTs"][0])
        else:
            myTime = startTime
        
        try:
            (res, reservations) = session.bcgi.getReservations(session.bewator_session, obj, myTime)
        except Exception:
            # Assume logged out if exception is thrown, log the exception and relogin user.
            print('-'*60)
            traceback.print_exc(file=sys.stdout)
            print('-'*60)
            
            return relogin(request)
        
        if res == 49:
            return relogin(request)
        
        if res != 48:
            print("ERROR: Res was something not OK, throw relogin (" + str(res) +")")
            return relogin(request)
        
        # Mark reservations in the past as "3".
        for r in reservations:
            if r.endTs < nowTime:
                r.state = 3
        
        nextTs = myTime + 86400 * 7
        prevTs = myTime - 86400 * 7
        
        return env.get_template("reservations.html").render(siteRenderArgs, object=obj, curTs=myTime, prevTs=prevTs, nextTs=nextTs,
                                                            reservations=reservations).encode("utf-8")

class MakeReservation(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return relogin(request)

        if not "start" in request.args or not "end" in request.args:
            return badRequest(request, "parameter error")

        if not "object" in request.args:
            return badRequest(request, "no object specified")

        obj = request.args["object"][0]
        
        start = request.args["start"][0]
        end = request.args["end"][0]
        
        if not start.isdigit() or not end.isdigit() or not obj.isdigit():
            return badRequest(request, "nasty-error!")
        
        obj = int(obj)
        start = int(start)
        end = int(end)
        
        res = session.bcgi.makeReservation(session.bewator_session, obj, start, end)

        if (res == 48):
            return "All ok!"

        if (res == 49):
            return relogin(request)
        
        if (res == 50):
            return bewatorRequestError(request, "Someone has reserved this time already. Sorry.")
        
        if (res == 51):
            return bewatorRequestError(request, "Max number of reservations reached for your group.")
        
        if (res == 52):
            return bewatorRequestError(request, "Time interval no longer available.")
        
        if (res == 53):
            return bewatorRequestError(request, "Max number of reservations reached for this period.")
        
        if (res == 54):
            return bewatorRequestError(request, "Booking object is in service state, please try again later.")
        
        return bewatorRequestError(request, "Unknown error: %d" % (res, ))

class CancelReservation(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return relogin(request)

        if not "start" in request.args or not "object" in request.args:
            return badRequest(request, "parameter error")

        obj = request.args["object"][0]
        
        start = request.args["start"][0]
        
        if not start.isdigit() or not obj.isdigit():
            return badRequest(request, "nasty-error!")
        
        obj = int(obj)
        start = int(start)
        
        res = session.bcgi.cancelReservation(session.bewator_session, obj, start)
        
        if (res == 48):
            return "All ok!"
        
        # Else something else (probably tried to cancel someone else's reservation.
        # Not likely to happen, but..
        return bewatorRequestError(request, "You can only cancel your own reservations.")


if __name__ == "__main__":
    root = Index()
    root.putChild("index", Index())
    root.putChild("loading.gif", static.File("static/loading.gif"))
    root.putChild("style.css", static.File("static/style.css"))
    root.putChild("beware.js", static.File("static/beware.js"))
    root.putChild("login", Login())
    root.putChild("objects", ListObjects())
    root.putChild("reservations", ListReservations())
    root.putChild("reserve", MakeReservation())
    root.putChild("cancel", CancelReservation())
    
    import sys
    
    if len(sys.argv) < 2:
        print("error: Please give target host as first and only argument to ", sys.argv[0], file=sys.stderr, sep="")
        sys.exit(1)
    
    URL = sys.argv[1]
    
    if (len(sys.argv)) == 3:
        siteRenderArgs['siteTitle'] = sys.argv[2].decode("utf-8")
    else:
        siteRenderArgs['siteTitle'] = u"Beware Bewator"
    
    reactor.listenTCP(31337, server.Site(root))
    reactor.run()
