# -*- coding: utf-8 -*-
from __future__ import print_function

from twisted.internet import reactor, threads
from twisted.web import static, server, html
from twisted.web.resource import Resource
from datetime import datetime, timedelta

from bewatorcgi import BewatorCgi

import os, inspect, getopt

# Templating
from jinja2 import Environment, PackageLoader

URL = "localhost"

from os.path import dirname

curdir = dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

env = Environment(loader=PackageLoader('beware', 'templates'))

siteRenderArgs = {}

def doTranslation(lang):
    global siteRenderArgs
    
    # defaults
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    navitext = { 'next': "Next -->", 'prev': "<-- Prev", 'logout': "Logout", 'submit': 'Login',\
                'tagid': 'Tag ID / Username', 'password': 'Password / PIN', 'login-banner': "Please login" }
    
    # overrides
    if lang == 'se':
        weekdays = ['M', 'T', 'O', 'T', 'F', 'L', 'S']
        navitext = { "next": u"Framåt -->", "prev": u"<-- Bakåt", "logout": u"Logga ut", "submit": u"Logga in",\
                     "tagid": u"Tagg-ID / Användarnamn", 'password': u"Lösenord / PIN", "login-banner": u"Logga in" }

    
    siteRenderArgs['weekdays'] = weekdays
    siteRenderArgs['navitext'] = navitext

def badRequest(request, errorText):
    template = env.get_template("error.html")
    request.setResponseCode(400)
    return template.render(siteRenderArgs, error=errorText).encode("utf-8")

def bewatorRequestError(request, errorText):
    request.setResponseCode(418) # I'm a teapot!
    return str(errorText)

def relogin(request):
    request.setResponseCode(401)
    return "Please login again"
    
def sessionExpired(request):
    return toUrl("index?error=Session%20expired,%20please%20login%20again.", request)

def toUrl(url, request):
    return "<script type=\"text/javascript\">window.location.replace(\"" + url + "\");</script>"
    
def defaultErrback(failure, request):
    failure.printTraceback()
    
    print(failure)
    
    # We usually assume logged out on failure
    request.write(relogin(request))
    request.finish()
    return None

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
    def async_finish(self, sessionId, request):
        user = request.getSession().user
        
        if sessionId < 0:
            print("Login failed for user " + user + " from " + str(request.getClientIP()))
            request.setResponseCode(401)
            request.write("Login failed")
            request.finish()
            return None
        
        print("Login successful for user " + user + " from " + str(request.getClientIP()))
        
        request.getSession().bewator_session = int(sessionId)
        
        request.write(toUrl("objects", request))
        request.finish()

    def render_POST(self, request):
        if not "user" in request.args or not "password" in request.args:
            return badRequest(request, "Please don't call me without the proper parameters!")
        
        user = request.args["user"][0]
        password = request.args["password"][0]
        
        session = request.getSession()
        session.user = user
        session.bcgi = BewatorCgi(URL)

        d = threads.deferToThread(session.bcgi.login, html.escape(user), password)
        d.addCallback(self.async_finish, request)
        d.addErrback(defaultErrback, request)
        
        return server.NOT_DONE_YET

class Logout(Resource):
    def render_GET(self, request):
        request.getSession().expire()
        return toUrl("index", request)

class ListObjects(Resource):
    def async_errback(self, failure, request):
        failure.printTraceback()
        
        # We usually assume logged out on failure
        sessionExpired(request)
        request.finish()
        return None
    
    def async_finish(self, objects, request):
        template = env.get_template("objects.html")
        request.write(template.render(siteRenderArgs, objects=objects).encode("utf-8"))
        request.finish()
    
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return sessionExpired(request)
        
        d = threads.deferToThread(session.bcgi.getBookingObjects, session.bewator_session)
        d.addCallback(self.async_finish, request)
        d.addErrback(self.async_errback, request)
        
        return server.NOT_DONE_YET
    
class ListReservations(Resource):
    def async_finish(self, tup, request, obj, nowTime, myTime):
        (res, reservations) = tup
        
        if res == 49:
            request.write(relogin(request))
            request.finish()
            return
        
        if res != 48:
            print("ERROR: Res was something not OK, throw relogin (" + str(res) +")")
            request.write(relogin(request))
            request.finish()
            return
        
        # Mark reservations in the past as "3".
        for r in reservations:
            if r.endTs < nowTime:
                r.state = 3
        
        nextTs = myTime + 86400 * 7
        prevTs = myTime - 86400 * 7
        
        request.write(env.get_template("reservations.html").render(siteRenderArgs, object=obj, curTs=myTime, prevTs=prevTs, nextTs=nextTs,
                                                            reservations=reservations).encode("utf-8"))
        request.finish()
        
    
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
        elif hasattr(session, "my_time"):
            myTime = session.my_time
        else:
            myTime = startTime
        
        session.my_time = myTime
        
        d = threads.deferToThread(session.bcgi.getReservations, session.bewator_session, obj, myTime)
        d.addCallback(self.async_finish, request, obj, nowTime, myTime)
        d.addErrback(defaultErrback, request)

        return server.NOT_DONE_YET

class MakeReservation(Resource):
    def async_finish(self, res, request):
        if (res == 48):
            request.write("All ok!")
        elif (res == 49):
            request.write(relogin(request))
        elif (res == 50):
            request.write(bewatorRequestError(request, "Someone has reserved this time already. Sorry."))
        elif (res == 51):
            request.write(bewatorRequestError(request, "Max number of reservations reached for your group."))
        elif (res == 52):
            request.write(bewatorRequestError(request, "Time interval no longer available."))
        elif (res == 53):
            request.write(bewatorRequestError(request, "Max number of reservations reached for this period."))
        elif (res == 54):
            request.write(bewatorRequestError(request, "Booking object is in service state, please try again later."))
        else:
            request.write(bewatorRequestError(request, "Unknown error: %d" % (res, )))
        
        request.finish()
    
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
        
        d = threads.deferToThread(session.bcgi.makeReservation, session.bewator_session, obj, start, end)
        d.addCallback(self.async_finish, request)
        d.addErrback(defaultErrback, request)
        
        return server.NOT_DONE_YET

class CancelReservation(Resource):
    def async_finish(self, res, request):
        if (res == 48):
            request.write("All ok!")
        else:
            # Else something else (probably tried to cancel someone else's reservation.
            # Not likely to happen, but..
            request.write(bewatorRequestError(request, "You can only cancel your own reservations."))
        
        request.finish()

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
        
        d = threads.deferToThread(session.bcgi.cancelReservation, session.bewator_session, obj, start)
        d.addCallback(self.async_finish, request)
        d.addErrback(defaultErrback, request)
        
        return server.NOT_DONE_YET

if __name__ == "__main__":
    root = Index()
    root.putChild("index", Index())
    root.putChild("loading.gif", static.File(curdir + "/static/loading.gif"))
    root.putChild("style.css", static.File(curdir + "/static/style.css"))
    root.putChild("beware.js", static.File(curdir + "/static/beware.js"))
    root.putChild("login", Login())
    root.putChild("logout", Logout())
    root.putChild("objects", ListObjects())
    root.putChild("reservations", ListReservations())
    root.putChild("reserve", MakeReservation())
    root.putChild("cancel", CancelReservation())
    
    def usage():
        print("usage: ", sys.argv[0], " -H <bewator-applet-url> [-t <title>] [-p <port>]", file=sys.stderr, sep="")
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hH:t:p:l:c:", ["help"])
    except getopt.GetoptError as err:
        # print help information and exit:
        usage()
        print(str(err), file=sys.stderr, sep="") # will print something like "option -a not recognized"
        sys.exit(2)
    
    host = None
    port = 31337
    siteTitle = u"Beware Bewator"
    
    customCss = False
    
    doTranslation("default")
    
    for o, a in opts:
        if o == "-v":
            verbose = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o == "-H":
            host = a
        elif o == "-t":
            siteTitle = a.decode("utf-8")
        elif o == "-p":
            port = int(a)
        elif o == "-l":
            doTranslation(a)
        elif o == "-c":
            root.putChild("custom.css", static.File(curdir + "/static/" + a))
            customCss = True
        else:
            assert False, "unhandled option"

    if not customCss:
        root.putChild("custom.css", static.File(curdir + "/static/custom.css"))

    if host is None:
        usage()
        sys.exit(2)
        
    URL = host
    
    siteRenderArgs['siteTitle'] = siteTitle
    
    print("Starting Beware!\n\nURL = \"" + URL + "\"\nPort = " + str(port) + "\nTitle = \"" + siteTitle + "\"\n")
    
    reactor.listenTCP(port, server.Site(root))
    reactor.run()
