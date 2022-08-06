session_id = self.set_session()

try:
    if (self.session_authenticated(session_id)):
        self.redirect("/dashboard")
    else:
        self.execute_template("/login.html", parameters)
except:
    self.redirect("/initialize")
