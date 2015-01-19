# -*- coding: utf-8 -*-
from twisted.internet import reactor
from twisted.web import static, server
from twisted.web.resource import Resource
from datetime import datetime, timedelta

from bewatorcgi import BewatorCgi

# Templating
from jinja2 import Environment, PackageLoader

URL = "81.224.81.68"

env = Environment(loader=PackageLoader('beware', 'templates'))

def simpleError(errorText):
    template = env.get_template("error.html")
    return template.render(error=errorText).encode("utf-8")

def toIndex(request):
    request.redirect("/")
    request.finish()
    return server.NOT_DONE_YET

class Index(Resource):
    def getChild(self, name, request):
        if name == '':
            return self
        return Resource.getChild(self, name, request)
    
    def render_GET(self, request):
        template = env.get_template('index.html')
        
        return template.render().encode("utf-8")

class Login(Resource):
    def render_POST(self, request):
        if not "user" in request.args or not "password" in request.args:
            return toIndex(request)
        
        user = request.args["user"][0]
        password = request.args["password"][0]
        
        if not user.isdigit() or not password.isdigit():
            return simpleError("nasty-error!")
        
        session = request.getSession()
        session.bcgi = BewatorCgi(URL)
        sessionId = session.bcgi.login(user, password)
        
        if sessionId < 0:
            return simpleError("Login error")
        
        print "Login successful for user " + user + " from " + str(request.getClientIP())
        
        session.bewator_session = int(sessionId)
        
        request.redirect("objects")
        request.finish()
        
        return server.NOT_DONE_YET

class ListObjects(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return toIndex(request)
        
        objects = session.bcgi.getBookingObjects(session.bewator_session)
        
        template = env.get_template("objects.html")
        return template.render(objects=objects).encode("utf-8")

class ListReservations(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return toIndex(request)

        if not "object" in request.args:
            return simpleError("no object specified")

        obj = request.args["object"][0]

        if not obj.isdigit():
            return simpleError("nasty-error!")

        if "fromTs" in request.args and request.args["fromTs"][0].isdigit():
            myTime = int(request.args["fromTs"][0])
            prevTs = myTime - 86400 * 7
        else:
            dt = datetime.now()
        
            #dt -= timedelta(days = dt.weekday(), seconds=dt.second, hours=dt.hour, minutes = dt.minute, microseconds = dt.microsecond)
        
            myTime = int((dt - datetime(1990, 1, 1, 0, 0)).total_seconds())
            prevTs = None

        obj = int(obj)

        reservations = session.bcgi.getReservations(session.bewator_session, obj, myTime)
        
        nextTs = myTime + 86400 * 7
        
        return env.get_template("reservations.html").render(object=obj, prevTs=prevTs, nextTs=nextTs,
                                                            reservations=reservations).encode("utf-8")

class Reserve(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return toIndex(request)

        if not "start" in request.args or not "end" in request.args:
            return simpleError("parameter error")

        if not "object" in request.args:
            return simpleError("no object specified")

        obj = request.args["object"][0]
        
        start = request.args["start"][0]
        end = request.args["end"][0]
        
        if not start.isdigit() or not end.isdigit() or not obj.isdigit():
            return simpleError("nasty-error!")
        
        obj = int(obj)
        start = int(start)
        end = int(end)
        
        res = session.bcgi.reserve(session.bewator_session, obj, start, end)
        
        if (res == 48):
            request.redirect("objects")
            request.finish()
            
            return server.NOT_DONE_YET
        
        return simpleError("Error in reserve: %d" % (res, ))

class CancelReservation(Resource):
    def render_GET(self, request):
        session = request.getSession()
        if not hasattr(session, "bewator_session"):
            return toIndex(request)

        if not "start" in request.args or not "object" in request.args:
            return simpleError("parameter error")

        obj = request.args["object"][0]
        
        start = request.args["start"][0]
        
        if not start.isdigit() or not obj.isdigit():
            return simpleError("nasty-error!")
        
        obj = int(obj)
        start = int(start)
        
        res = session.bcgi.cancelReservation(session.bewator_session, obj, start)
        
        if (res == 48):
            request.redirect("objects")
            request.finish()
            
            return server.NOT_DONE_YET
        
        return simpleError("Error in cancel: %d" % (res, ))

root = Index()
root.putChild("style.css", static.File("static/style.css"))
root.putChild("login", Login())
root.putChild("objects", ListObjects())
root.putChild("reservations", ListReservations())
root.putChild("reserve", Reserve())
root.putChild("cancel", CancelReservation())


reactor.listenTCP(31337, server.Site(root))
reactor.run()
