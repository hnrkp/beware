from datetime import datetime, timedelta

class reservation(object):
    def __init__(self, obj, tsFrom, tsTo, state):
        self.object = obj
        self.startTs = int(tsFrom)
        self.endTs = int(tsTo)
        self.state = state
        self.start = datetime(1990, 1, 1, 0, 0) + timedelta(seconds=self.startTs)
        self.end = datetime(1990, 1, 1, 0, 0) + timedelta(seconds=self.endTs)

    
    def getDescriptiveString(self):
        state = ['Free', 'Reserved', 'Reserved by you']
        
        return str(self.start) + " - " + str(self.end.time()) + ": " + state[self.state]
    