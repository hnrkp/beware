# -*- coding: utf-8 -*-
from twisted.internet import reactor
from twisted.web import static, server
from twisted.web.resource import Resource

from bewatorcgi import BewatorCgi

# Templating
from jinja2 import Environment, PackageLoader

URL = "81.224.81.68"

env = Environment(loader=PackageLoader('beware', 'templates'))

def simpleError(errorText):
    template = env.get_template("error.html")
    return template.render(error=errorText).encode("utf-8")

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
            return simpleError("wtf?")
        
        user = request.args["user"][0]
        password = request.args["password"][0]
        
        if not user.isdigit() or not password.isdigit():
            return simpleError("nasty-error!")
        
        session = BewatorCgi(URL).login(user, password)
        
        if session < 0:
            return simpleError("Login error")
        
        request.getSession().bewator_session = session
        
        request.redirect("objectlist")
        request.finish()
        
        return server.NOT_DONE_YET

class ListObjects(Resource):
    def render_GET(self, request):
        session = request.getSession().bewator_session
        
        objects = BewatorCgi(URL).listObjects(session)
        
        template = env.get_template("objectlist.html")
        return template.render(objects=objects).encode("utf-8")

root = Index()

root.putChild("style.css", static.File("static/style.css"))
root.putChild("login", Login())
root.putChild("objectlist", ListObjects())

reactor.listenTCP(31337, server.Site(root))
reactor.run()
