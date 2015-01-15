from twisted.internet import reactor
from twisted.web import static, server
from twisted.web.resource import Resource

import cgi
from bewatorcgi import BewatorCgi

URL = "81.224.81.68"

class Login(Resource):
    def render_GET(self, request):
        if not "user" in request.args or not "password" in request.args:
            return "wtf?"
        
        user = request.args["user"][0]
        password = request.args["password"][0]
        
        if not user.isdigit() or not password.isdigit():
            return "nasty-error!"
        
        session = BewatorCgi(URL).login(user, password)
        
        if session < 0:
            return "Login error!"
        
        request.getSession().bewator_session = session
        
        return "hello " + user + "! pass: " + password + " session: " + str(session)

class ListObjects(Resource):
    def render_GET(self, request):
        session = request.getSession().bewator_session
        
        objects = BewatorCgi(URL).listObjects(session)
        
        return "Objects: " + " ".join(map(lambda x:x[1], objects))

root = static.File("static/")

root.putChild("login", Login())
root.putChild("objectlist", ListObjects())

reactor.listenTCP(31337, server.Site(root))
reactor.run()
