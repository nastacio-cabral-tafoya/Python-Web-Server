session_id = self.set_session()

try:
    if (HTTPHandler.active_sessions[session_id]["parameters"]["authenticated"]):
        self.redirect("/dashboard")
    else:
        self.redirect("/login")
except:
    self.redirect("/initialize")
