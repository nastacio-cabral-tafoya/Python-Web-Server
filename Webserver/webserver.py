import os
import json
import socket
import secrets
import datetime
import subprocess

#Changes current working directory to the location of the script.
absolute_path = ""

for location in os.path.realpath(__file__).split('\\')[:-1]:
    absolute_path += (location + '/')

os.chdir(absolute_path)
print(os.getcwd())

def is_blank(string):
    for ch in string:
        if ((ord(ch) >= 32) and (ord(ch) <= 126)):
            return (False)
    return (True)

#Class that handles http requests and responses.
class HTTPHandler:
    active_sessions = {}
    
    # Initializes the HTTPHandler Object.
    def __init__(self, client_request, request_origin):
        # Initializes the class working values.
        self.config            = {}
        self.origin            = request_origin
        self.http_request      = client_request
        self.http_request_data = ""
        self.execution_stdout  = ""
        self.request           = {}
        self.response_headers  = {}
        self.response_cookies  = []
        self.response_body     = ""
        self.response          = None

        self.import_config()
        self.parse_request()  # Parses the http request into a dictionary.
        self.handle_request() # Determines what to do with the request, and what to respond to the client with.

    # Imports settings for the HTTPHandler such as default page, paths, etc.
    def import_config(self, path = "Server_Config/config.json"):
        #print("import-config")

        with open(path, 'r') as f_in:
                self.config = json.loads(f_in.read())
    
    #Parses the http request into a dictionary.
    def parse_request(self):
        #print("parse-request")
        # Parses the first line of the request. The first line contains the request type, path, and protocol version.
        self.http_request_data = self.http_request.split('\n')
        data                   = self.http_request_data[0].split(' ')
        self.request["type"]   = data[0]

        # Parses the path, and the parameters sent in the path.
        try:
            get_data                        = data[1].split('?')
            self.request["path"]            = get_data[0]
            self.request["path-parameters"] = get_data[1]

        except:
            try:
                self.request["path"]            = data[1].split('?')[0]
                self.request["path-parameters"] = ""
            except:
                self.request["path"]            = "/"
                self.request["path-parameters"] = ""

        # Sets the protocol.
        self.request["protocol"] = data[2]

        # Parses the http header values.
        for item in self.http_request_data[1:-1]:
            try:
                try:
                    (key, data)       = item.split(':')

                    if (data[0] == ' '):
                        data = data[1:]

                    if (key == "Cookie"):
                        self.request[key] = {}

                        for cookie in data.split(';'):
                            (cookie_name, cookie_value)    = cookie.split('=')
                            self.request[key][cookie_name] = cookie_value.replace('\r', '')

                    else:
                        self.request[key] = data.replace("; ", ';')
                except:
                    self.request[item.split(':')[0]] = ""
            except:
                print("Cannot Parse -> " + item)
                
        # Parses the request data.
        self.request["parameters"] = self.http_request_data[len(self.http_request_data) - 1]

    def redirect(self, path):
        self.set_response_header("Location", path)
        self.set_response(body = "", status = "301 Moved Permanently")

    def set_error(self, code, parameters, method):
        self.execute_action(self.config["status-locations"][code], parameters, method, status = (code + " " + self.config["status-codes"][code]))
    
    # Adds information to the response.
    def set_response(self, body = None, status = "200 OK"):
        #print("set-response")

        if (self.response == None):
            self.response = (self.config["version"] + ' ' + status + '\n').encode()

            if (len(self.response_cookies) > 0):
                self.response += "Access-Control-Expose-Headers: *\n".encode()
            
            for i, key in enumerate(self.response_headers):
                if (i > 0):
                    self.response += '\n'.encode()
                self.response += (key + ": " + self.response_headers[key]).encode()

            if (len(self.response_cookies) > 0):
                for i, cookie in enumerate(self.response_cookies):
                    if (i > 0):
                        self.response += ' '.encode()
                    self.response += ("\nSet-Cookie: " + cookie).encode()

            self.response += "\r\n\r\n".encode()
            
            if not(body == None):
                try:
                    self.response += body.encode()
                except:
                    self.response += body
            else:
                self.response += (self.response_body.encode() + '\r'.encode())

    def set_response_header(self, key, value):
        self.response_headers[key] = value
    
    def set_session(self):
        ret_val = None
        
        try:
            if (self.request["Cookie"]["sessionId"] in HTTPHandler.active_sessions):
                ret_val = self.request["Cookie"]["sessionId"]
            else:
                raise Exception("No Session Exists")
        except:
            set_date   = datetime.datetime.now()
            session_id = secrets.token_urlsafe(16)

            while (session_id in HTTPHandler.active_sessions):
                session_id = secrets.token_urlsafe(64)

            HTTPHandler.active_sessions[session_id] = {"set-date":set_date, "timeout":self.config["session-timeout"], "parameters":{}}
            ret_val                                 = session_id
            self.set_cookie("sessionId", session_id)

        return (ret_val)

    def set_cookie(self, key, value):
        self.response_cookies.append(key + '=' + value)

    def print(self, text, end = '\n'):
        self.response_body += (text + end)

    def get_exec_stdout(self):
        return (self.execution_stdout)
    
    def template_print(self, string, end = '\n'):
        self.execution_stdout += (string + end)

    def reset_exec_stdout(self):
        self.execution_stdout = ""

    def execute_template(self, path, parameters):
        #print("execute-template")
        template   = ""
        holder     = ""
        scripts    = []
        found_code = False
        i          = 0
        result     = ""
        
        with open((self.config["root-path"] + self.config["paths"]["templates"] + path), 'r') as f_in:
            template = f_in.read()

        while (i < len(template)):
            if (template[i] == '<'):
                if not(i == (len(template) - 2)):
                    if (template[i + 1] == '%'):
                        j = (i + 2)

                        while (j < (len(template) - 1)):
                            if (template[j] == '%'):
                                if not(j == (len(template) - 1)):
                                    if (template[j + 1] == '>'):
                                        result += ("%>" + str(len(scripts)) + "<%")

                                        scripts.append(holder)

                                        holder  = ""
                                        i       = (j + 1)
                                        break
                                    else:
                                        holder += template[j]
                                else:
                                    holder += template[j]
                            else:
                                holder += template[j]
                            j += 1
                    else:
                        result += template[i]
                else:
                    result += template[i]
            else:
                result += template[i]
            i += 1

        for s, script in enumerate(scripts):
            lines      = script.split('\n')
            code_lines = []

            for line in lines:
                if not(is_blank(line)):
                    code_lines.append(line.replace('\t', '    '))
                    
            indent = 0

            while ((code_lines[0][indent] == '\t') or (code_lines[0][indent] == ' ')):
                indent += 1

            corrected = ""
            
            for line in code_lines:
                corrected += (line[indent:].replace('\t', "    ") + '\n')
            
            exec(corrected)

            result = result.replace(("%>" + str(s) + "<%"), self.get_exec_stdout())
            self.reset_exec_stdout()
        
        self.set_response_header("Content-Type", "text/html")
        self.set_response_header("Content-Length", str(len(result)))
        self.print(result)
    
    # Determines what to do with a request.
    def handle_request(self):
        #print("handle-request")
        if (self.request["type"] == "GET"):
            self.do_get(self.request["path"], self.request["path-parameters"])
        elif (self.request["type"] == "POST"):
            self.do_post(self.request["path"], self.request["parameters"])
        elif (self.request["type"] == "PUT"):
            self.do_put(self.request["path"], self.request["parameters"])
        elif (self.request["type"] == "DELETE"):
            self.do_delete(self.request["path"], self.request["parameters"])

    # Does a get method. It is in a separate function so that additional stuff can be added if required before an action is executed.
    def do_get(self, path, args):
        #print("do-get")
        if (path == "/"):
            self.execute_action(self.config["default-location"], args, method = "get")
        else:
            self.execute_action(path, args, method = "get")

    # Does a post method. It is in a separate function so that additional stuff can be added if required before an action is executed.
    def do_post(self, path, args):
        #print("do-post")
        self.execute_action(path, args, method = "post")

    # Does a put method. It is in a separate function so that additional stuff can be added if required before an action is executed.
    def do_put(self, path, args):
        #print("do-put")
        self.execute_action(path, args, method = "put")

    # Does a delete method. It is in a separate function so that additional stuff can be added if required before an action is executed.
    def do_delete(self, path, args):
        #print("do-delete")
        self.execute_action(path, args, method = "delete")

    # Executes an action. The default method if one is not specified is get.
    def execute_action(self, action, args, method = "get", status = "200 OK"):
        #print("execute-action")
        # Parses the parameters from the http request that need to be passed as args to the `action`.
        parameters    = {}
        action_script = ""
        
        for arg in args.split('&'):
            # Replaces the url escape codes with the characters that they escape.
            try:
                (key, value)    = arg.split('=')
                parameters[key] = value.replace('+', ' ').replace("%20", ' ').replace("$20", ' ').replace("%3C", '<').replace("$3C", '<').replace("%3E", '>').replace("$3E", '>').replace("%23", '#').replace("$23", '#').replace("%25", '%').replace("$25", '%').replace("%2B", '+').replace("$2B", '+').replace("%7B", '{').replace("$7B", '{').replace("%7D", '}').replace("$7D", '}').replace("%7C", '|').replace("$7C", '|').replace("%5C", '\\').replace("$5C", '\\').replace("%5E", '^').replace("$5E", '^').replace("%7E", '~').replace("$7E", '~').replace("%5B", '[').replace("$5B", '[').replace("%5D", ']').replace("$5D", ']').replace("%60", '\'').replace("$60", '\'').replace("%3B", ';').replace("$3B", ';').replace("%2F", '/').replace("$2F", '/').replace("%3F", '?').replace("$3F", '?').replace("%3A", ':').replace("$3A", ':').replace("%40", '@').replace("$40", '@').replace("%3D", '=').replace("$3D", '=').replace("%26", '&').replace("$26", '&').replace("%24", '$').replace("$24", '$')
            except:
                parameters[arg.split('=')[0]] = None
        
        # Attempts to execute the action as a python script.
        try:
            with open((self.config["root-path"] + self.config["paths"]["actions"]["actions-root"] + self.config["paths"]["actions"][method] + action + ".py"), 'r') as f_in:
                action_script = f_in.read()

            # Setting http headers.
            self.set_response_header("Content-Type", "text/html")
            exec(action_script)
            self.set_response_header("Content-Length", str(len(self.response_body.encode())))
            
            self.set_response(status = status)
        except FileNotFoundError as fnfe:
            self.get_file_bytes(action, method)
        except Exception as general_exception:
            print(general_exception)
            self.set_error("500", ("path=" + action.replace('/', "%2F")), method)

    # Gets the bytes of a file that matches the path from the url and puts them in the response.
    def get_file_bytes(self, path, method = "get", status = "200 OK"):
        #print("get-file-bytes")
        try:
            # Reading file bytes.
            f_in = open((self.config["root-path"] + self.config["paths"]["public-files"] + path), "rb")
            file_bytes = f_in.read()

            # Setting http headers.
            self.set_response_header("Content-Type", self.config["content-types"][path.split('.')[-1:][0]])
            self.set_response_header("Content-Length", str(len(file_bytes)))

            # Setting http response.
            self.set_response(body = file_bytes, status = status)
            f_in.close()
        except:
            # If the bytes cannot be read, a 404 error is returned because the path does not exist.
            self.set_error("404", ("path=" + path.replace('/', "%2F")), method)
    
    # Static method that can be accessed without instantiating the class as an object.
    # The class does not need to be instantiated as an object to be used external to the class.
    # The object for the class only exists within the instance of the static method.
    def process_request(client_request, request_origin):
        #print("process-request")
        handler = HTTPHandler(client_request, request_origin)
        return(handler.response)
#END HTTPHandler Class

# Define socket host and port
SERVER_HOST = "2605:59c0:daa6:2700:8dda:5405:e803:bf2f"
SERVER_PORT = 80

# Create socket
server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((SERVER_HOST, SERVER_PORT))
server_socket.listen(1)

print("Listening on port " + str(SERVER_PORT) + ". . .")

while True:    
    # Wait for client connections
    client_connection, client_address = server_socket.accept()

    # Get the client request
    client_request  = client_connection.recv(1024).decode()
    server_response = HTTPHandler.process_request(client_request, client_address)
    
    # Send HTTP response
    client_connection.sendall(server_response)
    client_connection.close()

# Close socket
server_socket.close()
