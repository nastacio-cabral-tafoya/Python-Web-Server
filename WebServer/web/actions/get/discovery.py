session_id = self.set_session()

try:
    if (self.session_authenticated(session_id) and self.validate_session(session_id)):
        parameters["username"] = self.get_session_parameter(session_id, "username")
        self.execute_template("/discovery.html", parameters)
    else:
        self.redirect("/login")
except:
    self.redirect("/initialize")
