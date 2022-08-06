session_id = self.set_session()
data = json.loads(parameters["data"])

try:
    if(self.validate_session(session_id)):
        self.deauthenticate_session(session_id)
    else:
        self.destroy_session(session_id)
except:
    pass

self.print("{\"stat\": 0, \"msg\":\"User de-authenticated!\"}")
