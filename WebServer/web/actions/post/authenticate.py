session_id = self.set_session()
data = json.loads(parameters["data"])

if not(self.config["configured"]):
    if ((data["username"][0] == "admin") and (data["password"][0] == "pjelly")):
        if (self.validate_session(session_id)):
            self.authenticate_session(session_id, data["username"][0])
            self.print("{\"stat\": 0, \"msg\": \"User Successfully Authenticated\"}")
        else:
            del HTTPHandler.active_sessions[session_id]
            self.print("{\"stat\": 3, \"msg\": \"One or more of the required fields were filled out incorrectly.\\n\\nPlease check your entries and try again.\"}")

    elif (is_blank(data["username"][0]) or is_blank(data["password"][0])):
        errors = ""
        
        for item in data:
            if (is_blank(data[item][0])):
                if (len(errors) > 0):
                    errors += ", "

                errors += ("\"" + data[item][1] + "\"")

        self.print("{\"stat\": 2, \"msg\": \"One or more of the required fields were filled out incorrectly.\\n\\nPlease check your entries and try again.\", \"incorrect_fields\": [" + errors + "]}")
    else:
        self.print("{\"stat\": 1, \"msg\": \"Unable to Authenticate User\"}")
