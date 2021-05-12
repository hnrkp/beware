# -*- coding: utf-8 -*-


from twisted.internet import reactor, threads
from twisted.web import static, server, html
from twisted.web.resource import Resource
from datetime import datetime, timedelta
from uuid import uuid4

from bewatorcgi import BewatorCgi

import sys, os, inspect, getopt, logging

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
        navitext = { "next": "Framåt -->", "prev": "<-- Bakåt", "logout": "Logga ut", "submit": "Logga in",\
                     "tagid": "Tagg-ID / Användarnamn", 'password': "Lösenord / PIN", "login-banner": "Logga in" }

    
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
    return b"Please login again"
    
def sessionExpired(request):
    return toUrl(b"index?error=Session%20expired,%20please%20login%20again.", request)

def toUrl(url, request):
    return b"<script type=\"text/javascript\">window.location.replace(\"" + url + b"\");</script>"
    
def defaultErrback(failure, request):
    failure.printTraceback()
    
    logging.error(failure)
    
    # We usually assume logged out on failure
    request.write(relogin(request))
    request.finish()
    return None

def validateCsrfToken(session, request):
    token = request.getHeader(b'X-CSRF-Token').decode()
    
    if token != session.csrf_token:
        logging.error("token mismatch, %s vs %s" % (token, session.csrf_token))
        return False 
    
    return True

class Index(Resource):
    def getChild(self, name, request):
        if name == '':
            return self
        return Resource.getChild(self, name, request)
    
    def render_GET(self, request):
        template = env.get_template('index.html')
        
        error = None
        
        if b"error" in request.args:
            error = html.escape(request.args[b"error"][0].decode())
        
        return template.render(siteRenderArgs, error=error).encode("utf-8")

class Login(Resource):
    def async_errback(self, failure, request):
        failure.printTraceback()
        logging.warning(failure)
    
        request.setResponseCode(401)
        request.write(b"Login failed due to an error (server down?)")
        request.finish()
        return None

    def async_finish(self, sessionId, request):
        user = request.getSession().user
        
        if sessionId < 0:
            logging.info("Login failed for user " + user + " from " + str(request.getClientIP()))
            request.setResponseCode(401)
            request.write(b"Login failed")
            request.finish()
            return None
        
        logging.info("Login successful for user " + str(user) + " from " + str(request.getClientAddress()))
        
        request.getSession().bewator_session = int(sessionId)
        request.getSession().csrf_token = str(uuid4())
        
        request.write(toUrl(b"objects", request))
        request.finish()

    def render_POST(self, request):
        if not b"user" in request.args or not b"password" in request.args:
            return badRequest(request, b"Please don't call me without the proper parameters!")
        
        user = request.args[b"user"][0]
        password = request.args[b"password"][0]
        
        session = request.getSession()
        session.user = user
        session.bcgi = BewatorCgi(URL)

        d = threads.deferToThread(session.bcgi.login, html.escape(user.decode()), password)
        d.addCallback(self.async_finish, request)
        d.addErrback(self.async_errback, request)
        
        return server.NOT_DONE_YET

class Logout(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return sessionExpired(request)

        if not validateCsrfToken(session, request):
            return badRequest(request, "csrf token error")
        
        session.expire()
        return toUrl(b"index", request)

class ListObjects(Resource):
    def async_errback(self, failure, request):
        failure.printTraceback()
        logging.warning(failure)
    
        # We usually assume logged out on failure
        request.write(sessionExpired(request))
        request.finish()
        return None
    
    def async_finish(self, tup, request):
        (res, objects) = tup
        
        if res == 49:
            request.write(sessionExpired(request))
            request.finish()
            return
        
        if res != 48:
            logging.error("ERROR: Res in listobjects was something not OK, throw relogin (" + str(res) +")")
            request.write(sessionExpired(request))
            request.finish()
            return
        
        template = env.get_template("objects.html")
        request.write(template.render(siteRenderArgs, csrf_token = request.getSession().csrf_token,
                                      objects=objects).encode("utf-8"))
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
            logging.error("ERROR: Res in listresv was something not OK, throw relogin (" + str(res) +")")
            request.write(relogin(request))
            request.finish()
            return

        rd = []
        cur_d = []

        for r in reservations:
            # Mark reservations in the past as "3".
            if r.endTs < nowTime:
                r.state = 3
            
            if len(cur_d) > 0:
                if cur_d[0].start.date() != r.start.date():
                    rd.append(cur_d)
                    cur_d = []
            
            cur_d.append(r)
        
        if len(cur_d) > 0:
            rd.append(cur_d)

        nextTs = myTime + 86400 * 7
        prevTs = myTime - 86400 * 7

        request.write(env.get_template("reservations.html").render(siteRenderArgs, object=obj, curTs=myTime, prevTs=prevTs, nextTs=nextTs,
                                                            reservations=rd).encode("utf-8"))
        request.finish()
        
    
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return relogin(request)

        if not b"object" in request.args:
            return badRequest(request, "no object specified")

        obj = request.args[b"object"][0]

        if not obj.isdigit():
            return badRequest(request, "nasty-error!")

        if not validateCsrfToken(session, request):
            return badRequest(request, "csrf token error")

        obj = int(obj)

        dt = datetime.now()
        
        # for mondays..
        dt -= timedelta(days = dt.weekday(), seconds=dt.second, hours=dt.hour, minutes = dt.minute, microseconds = dt.microsecond)
        
        startTime = int((dt - datetime(1990, 1, 1, 0, 0)).total_seconds())
        nowTime = int((datetime.now() - datetime(1990, 1, 1, 0, 0)).total_seconds())

        if b"fromTs" in request.args and request.args[b"fromTs"][0].decode().isdigit():
            myTime = int(request.args[b"fromTs"][0].decode("ascii"))
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
            request.write(b"All ok!")
        elif (res == 49):
            request.write(relogin(request))
        elif (res == 50):
            request.write(bewatorRequestError(request, b"Someone has reserved this time already. Sorry."))
        elif (res == 51):
            request.write(bewatorRequestError(request, b"Max number of reservations reached for your group."))
        elif (res == 52):
            request.write(bewatorRequestError(request, b"Time interval no longer available."))
        elif (res == 53):
            request.write(bewatorRequestError(request, b"Max number of reservations reached for this period."))
        elif (res == 54):
            request.write(bewatorRequestError(request, b"Booking object is in service state, please try again later."))
        else:
            request.write(bewatorRequestError(request, b"Unknown error: %d" % (res, )))
        
        request.finish()
    
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return relogin(request)

        if not b"start" in request.args or not b"end" in request.args:
            return badRequest(request, "parameter error")

        if not b"object" in request.args:
            return badRequest(request, "no object specified")

        obj = request.args[b"object"][0].decode()
        
        start = request.args[b"start"][0].decode()
        end = request.args[b"end"][0]
        
        if not start.isdigit() or not end.isdigit() or not obj.isdigit():
            return badRequest(request, b"nasty-error!")
        
        if not validateCsrfToken(session, request):
            return badRequest(request, b"csrf token error")
        
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
            request.write(b"All ok!")
        else:
            # Else something else (probably tried to cancel someone else's reservation.
            # Not likely to happen, but..
            request.write(bewatorRequestError(request, b"You can only cancel your own reservations."))
        
        request.finish()

    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return relogin(request)

        if not b"start" in request.args or not b"object" in request.args:
            return badRequest(request, b"parameter error")

        obj = request.args[b"object"][0].decode()
        
        start = request.args[b"start"][0].decode()
        
        if not start.isdigit() or not obj.isdigit():
            return badRequest(request, b"nasty-error!")

        if not validateCsrfToken(session, request):
            return badRequest(request, b"csrf token error")

        obj = int(obj)
        start = int(start)
        
        d = threads.deferToThread(session.bcgi.cancelReservation, session.bewator_session, obj, start)
        d.addCallback(self.async_finish, request)
        d.addErrback(defaultErrback, request)
        
        return server.NOT_DONE_YET

if __name__ == "__main__":
    root = Index()
    root.putChild(b'', Index())
    root.putChild(b"index", Index())
    root.putChild(b"loading.gif", static.File(curdir + "/static/loading.gif"))
    root.putChild(b"style.css", static.File(curdir + "/static/style.css"))
    root.putChild(b"beware.js", static.File(curdir + "/static/beware.js"))
    root.putChild(b"login", Login())
    root.putChild(b"logout", Logout())
    root.putChild(b"objects", ListObjects())
    root.putChild(b"reservations", ListReservations())
    root.putChild(b"reserve", MakeReservation())
    root.putChild(b"cancel", CancelReservation())
    
    def usage():
        print("usage: ", sys.argv[0], " -H <bewator-applet-url> [-t <title>] [-p <port>] --logfile=file.log", file=sys.stderr, sep="")
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hH:t:p:l:c:", ["help", "logfile="])
    except getopt.GetoptError as err:
        # print help information and exit:
        usage()
        print(str(err), file=sys.stderr, sep="") # will print something like "option -a not recognized"
        sys.exit(2)
    
    host = None
    port = 31337
    siteTitle = "Beware Bewator"
    
    customCss = False
    
    doTranslation("default")
    
    logfilename = "beware.log"

    for o, a in opts:
        if o == "-v":
            verbose = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o == "-H":
            host = a
        elif o == "-t":
            siteTitle = a
        elif o == "-p":
            port = int(a)
        elif o == "-l":
            doTranslation(a)
        elif o == "-c":
            root.putChild(b"custom.css", static.File(curdir + "/static/" + a))
            customCss = True
        elif o == "--logfile":
            logfilename = a
        else:
            assert False, "unhandled option"

    if not customCss:
        root.putChild(b"custom.css", static.File(curdir + "/static/custom.css"))

    if host is None:
        usage()
        sys.exit(2)
        
    URL = host
    
    siteRenderArgs['siteTitle'] = siteTitle
   
    logfmt = "[%(asctime)s] %(message)s"
    formatter = logging.Formatter(logfmt)

    logging.basicConfig(format=logfmt, filename=logfilename, level=logging.DEBUG)
    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(formatter)

    logging.getLogger().addHandler(consoleHandler)

    logging.info("Starting Beware!\n\nURL = \"" + URL + "\"\nPort = " + str(port) + "\nTitle = \"" + siteTitle + "\"\n")
    reactor.listenTCP(port, server.Site(root))
    reactor.run()
