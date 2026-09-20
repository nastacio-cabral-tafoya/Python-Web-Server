# Python HTTP Server

A lightweight, custom HTTP/1.x server written in Python using the standard `socket` library and a custom `HTTPHandler` application layer.

The server provides:

* IPv4 TCP socket handling
* HTTP/1.x request parsing
* HTTPS/TLS support through a separate SSL server
* Thread-per-connection request processing
* Configurable maximum concurrent worker threads
* `Content-Length` request bodies
* HTTP/1.1 chunked request bodies
* Dynamic Python-based request actions
* Static file serving
* HTML templates with embedded Python
* Cookie-based sessions
* Session authentication state
* SQLite application database connections
* SQLite or MySQL server logging
* HTTP error handling
* Optional HTTP-to-HTTPS redirection
* Configurable response headers and cookies

---

## Architecture

The server is divided into two primary layers:

```text
                         ┌─────────────────────┐
                         │       CLIENT        │
                         │                     │
                         │ Browser / curl / API│
                         └──────────┬──────────┘
                                    │
                             HTTP / HTTPS
                                    │
                                    ▼
                 ┌──────────────────────────────────┐
                 │          SOCKET SERVER           │
                 │                                  │
                 │ webserver_ipv4.py                │
                 │ webserver_ipv4_ssl.py            │
                 └────────────────┬─────────────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │    listener()   │
                         │                 │
                         │ accept()        │
                         │ Semaphore       │
                         │ Thread()        │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │ _handle_client  │
                         └────────┬────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │ _recv_http_request()    │
                    │                         │
                    │ Headers                 │
                    │ Content-Length          │
                    │ Chunked transfer        │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │      HTTPHandler        │
                    │                         │
                    │ parse_request()         │
                    │ handle_request()        │
                    │ execute_action()        │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┴────────────────┐
                 │                                │
                 ▼                                ▼
        ┌──────────────────┐             ┌──────────────────┐
        │ Dynamic Action   │             │ Static File      │
        │                  │             │                  │
        │ actions/*.py     │             │ public files     │
        │ exec()           │             │ binary/text data │
        └────────┬─────────┘             └────────┬─────────┘
                 │                                │
                 └──────────────┬─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ HTTP Response   │
                       │                 │
                       │ Status          │
                       │ Headers         │
                       │ Cookies         │
                       │ Body            │
                       └────────┬────────┘
                                │
                                ▼
                         client.sendall()
                                │
                                ▼
                         Close connection
```

The socket layer accepts the connection and creates a worker thread. Each worker creates its own `HTTPHandler` instance because the handler contains mutable request and response state. 

---

# Components

## `webserver_ipv4.py`

The primary HTTP server.

Responsibilities include:

1. Loading server configuration
2. Establishing the server root path
3. Loading encryption keys
4. Loading the `HTTPHandler`
5. Creating the IPv4 TCP socket
6. Binding the configured address and port
7. Listening for connections
8. Limiting concurrent workers
9. Accepting clients
10. Creating worker threads
11. Receiving complete HTTP requests
12. Sending HTTP responses
13. Logging server activity and exceptions

The server creates an IPv4 TCP socket using:

```python
socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
```

and then calls `bind()` and `listen()`. 

---

## `webserver_ipv4_ssl.py`

The HTTPS version of the server.

It creates a TCP socket and then establishes a TLS server context:

```python
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(
    server_config["cert-location"],
    server_config["key-location"]
)
```

The socket is subsequently wrapped with:

```python
context.wrap_socket(
    tcp_socket,
    server_side=True,
    do_handshake_on_connect=False
)
```

The resulting SSL socket is passed to the same `listener()` function used by the non-SSL server. 

This allows the HTTP processing pipeline to remain largely independent of whether the underlying connection is plain TCP or TLS.

---

# `my_http_handler.py`

`HTTPHandler` provides the application-level HTTP processing layer.

Its primary workflow is:

```text
HTTP bytes
    │
    ▼
parse_request()
    │
    ▼
request dictionary
    │
    ▼
handle_request()
    │
    ▼
HTTP method dispatcher
    │
    ▼
do_get()
do_post()
do_put()
do_delete()
do_connect()
do_options()
do_trace()
do_patch()
    │
    ▼
execute_action()
    │
    ├── Dynamic Python action
    │
    └── Static file fallback
    │
    ▼
set_response()
    │
    ▼
HTTP response bytes
```

`respond_to_request()` initializes the handler state, parses the request, optionally modifies the request for SSL redirection, dispatches the request, and returns the generated response. 

---

# Request Processing

## 1. TCP Connection

The listener waits for an incoming connection:

```python
client_connection, client_address = _socket_.accept()
```

A ten-second socket timeout is then applied.

```python
client_connection.settimeout(10)
```

A daemon worker thread is created to process the connection. 

---

## 2. Thread Limiting

The server uses:

```python
Semaphore(server_config["max-threads"])
```

to limit the number of simultaneous worker threads.

The listener acquires a semaphore slot before accepting a client:

```text
                    listener()
                       │
                       ▼
               semaphore.acquire()
                       │
                       ▼
                  accept()
                       │
                       ▼
                worker thread
                       │
                       ▼
               request processing
                       │
                       ▼
               semaphore.release()
```

This prevents the server from creating an unlimited number of worker threads. 

---

# HTTP Request Reception

`_recv_http_request()` is responsible for receiving a complete HTTP request from the TCP socket.

The function first reads until:

```text
\r\n\r\n
```

is encountered.

This identifies the end of the HTTP header section.

It then examines:

* `Content-Length`
* `Transfer-Encoding`

The server supports three basic cases.

### No body

```text
HTTP headers
     │
     ▼
\r\n\r\n
     │
     ▼
Request complete
```

### Content-Length

```text
Headers
   │
   ▼
Content-Length: N
   │
   ▼
Read N bytes
   │
   ▼
Complete request
```

### Chunked transfer encoding

```text
Headers
   │
   ▼
Transfer-Encoding: chunked
   │
   ▼
Read chunk size
   │
   ▼
Read chunk
   │
   ▼
Repeat
   │
   ▼
Zero-size chunk
   │
   ▼
Read trailers
   │
   ▼
Reconstruct normal request
```

The server also rejects requests with both `Content-Length` and `Transfer-Encoding` and limits the initial header section to 1 MiB. 

---

# HTTP Request Parsing

After the complete request has been received, `HTTPHandler.parse_request()` converts the raw HTTP request into internal request data.

The request line is split into:

```text
METHOD PATH HTTP/VERSION
```

For example:

```text
GET /index.html HTTP/1.1
```

becomes conceptually:

```python
{
    "type": "GET",
    "path": "/index.html",
    "protocol": "HTTP/1.1"
}
```

The parser also extracts:

* Query parameters
* HTTP headers
* Cookies
* Request body
* Content-Length
* Content-Type
* Transfer-Encoding
* Host
* Connection

Cookies are converted into a dictionary for application use. 

---

# HTTP Methods

The handler recognizes:

```text
GET
HEAD
POST
PUT
DELETE
CONNECT
OPTIONS
TRACE
PATCH
```

The method is dispatched by `handle_request()`.

```text
                    HTTP request
                         │
                         ▼
                   handle_request()
                         │
             ┌───────────┼────────────┐
             │           │            │
             ▼           ▼            ▼
            GET         POST         PUT
             │           │            │
             └─────┬─────┴────────────┘
                   │
             Additional methods
                   │
                   ▼
            execute_action()
```

Unsupported methods generate a `405` response and an `Allow` header containing the supported methods. 

---

# GET Requests

For `GET`, the root path receives special handling.

```text
GET /
 │
 ▼
default-location
 │
 ▼
execute_action()
```

Other paths are passed directly to `execute_action()`.

```text
GET /some/path
 │
 ▼
execute_action("/some/path")
```



---

# HEAD Requests

`HEAD` follows the same action path as `GET`, but removes the response body after the response has been constructed.

```text
HEAD request
     │
     ▼
GET-style action
     │
     ▼
Build response
     │
     ▼
Remove body
     │
     ▼
Return headers
```



---

# Dynamic Actions

The server uses Python files as request actions.

The general path is:

```text
HTTP request
     │
     ▼
HTTP method
     │
     ▼
Action path
     │
     ▼
actions/<method>/<action>.py
     │
     ▼
Read Python source
     │
     ▼
exec(action_script)
     │
     ▼
Generate response body
```

`execute_action()` parses request parameters and attempts to load the corresponding Python action file.

If the action exists, its contents are executed using Python's `exec()`.

The action can therefore interact with the `HTTPHandler` instance and generate the response. 

---

# Static Files

If the corresponding Python action does not exist, the server falls back to `get_file_bytes()`.

```text
Action not found
      │
      ▼
get_file_bytes()
      │
      ▼
Open public file
      │
      ▼
Read bytes
      │
      ▼
Determine Content-Type
      │
      ▼
Set Content-Length
      │
      ▼
Build response
```

This allows URLs to resolve to ordinary static files in addition to Python actions.

If the requested file cannot be read, the handler generates a `404` error response. 

---

# Templates

The handler also supports templates containing embedded Python blocks.

Template code uses:

```text
<% ... %>
```

The template engine:

1. Loads the template
2. Searches for `<% ... %>` blocks
3. Extracts the Python code
4. Normalizes indentation
5. Executes the Python
6. Captures generated output
7. Inserts the output back into the template
8. Sets the response content type and length

Conceptually:

```text
Template
   │
   ├── HTML
   │
   ├── <% Python %>
   │
   ├── HTML
   │
   └── <% Python %>
          │
          ▼
     Execute Python
          │
          ▼
     Generated output
          │
          ▼
     Insert into HTML
          │
          ▼
     Final HTML response
```

The template engine uses `template_print()` and an internal execution-output buffer to capture generated content.  

---

# Sessions

`HTTPHandler` maintains sessions in the class-level:

```python
HTTPHandler.active_sessions
```

Access to the shared session dictionary is protected by:

```python
HTTPHandler.session_lock
```

which is an `RLock`.

Sessions contain:

```text
session ID
    │
    ├── set-date
    ├── timeout
    └── parameters
          │
          ├── authenticated
          └── username
```

A new session ID is generated with:

```python
secrets.token_urlsafe(64)
```

The session identifier is returned to the client as a cookie.

The cookie includes:

```text
Max-Age
SameSite=Strict
```

 

---

# Session Authentication

The handler provides methods for:

```text
set_session()
validate_session()
get_session_parameter()
set_session_parameter()
session_authenticated()
authenticate_session()
deauthenticate_session()
destroy_session()
```

Authentication state is stored in the session:

```python
{
    "authenticated": True/False,
    "username": "..."
}
```

Session methods are synchronized through the session lock. 

---

# Responses

Responses are assembled by `set_response()`.

The resulting HTTP message consists of:

```text
HTTP status line
        +
HTTP headers
        +
Set-Cookie headers
        +
blank line
        +
response body
```

For example:

```text
HTTP/1.1 200 OK\r\n
Content-Type: text/html\r\n
Content-Length: 123\r\n
Set-Cookie: session=...\r\n
\r\n
<html>...</html>
```

The response is stored as bytes in:

```python
self.response
```

and eventually sent through:

```python
client_connection.sendall(server_response)
```

 

---

# Error Handling

The server has multiple layers of error handling.

## 400-level request errors

Malformed HTTP requests can raise exceptions during request reception or parsing.

Examples include:

* Invalid HTTP request line
* Invalid HTTP header
* Invalid `Content-Length`
* Conflicting `Content-Length` headers
* Unsupported transfer encoding
* Incomplete request body
* Invalid chunk size
* Invalid chunk delimiter

---

## 404

If a requested static resource cannot be loaded:

```text
get_file_bytes()
      │
      ▼
Exception
      │
      ▼
set_error("404", ...)
```

---

## 405

Unsupported HTTP methods result in:

```text
405 Method Not Allowed
```

with an `Allow` header.

---

## 500

Exceptions occurring during dynamic action execution result in:

```text
500 Internal Server Error
```

The configured error action is executed through `set_error()`.

The error handler also prevents recursive error handling if the error resource itself fails. 

---

# Logging

Two logging mechanisms are present.

## Database logger

`logger()` supports:

```text
SQLite
MySQL
```

For SQLite, the logger:

* Opens the configured database
* Enables WAL mode
* Sets a busy timeout
* Loads `Server_Config/log.sql`
* Inserts the log record
* Commits the transaction
* Closes the connection

For MySQL, it connects using the configured MySQL connection parameters and inserts the log entry into the `log` table. 

---

## Text logger

`_logger_()` writes directly to:

```text
log.txt
```

If the file does not exist, it creates it.

This logger is used for some normal server response logging while the database logger is used for exceptions and other server events. 

---

# Configuration

The server loads:

```text
Server_Config/server_config.json
```

during startup.

The configuration supplies values used for:

```text
Server host
HTTP port
HTTPS port
Socket buffer size
Connection queue limit
Maximum worker threads
HTTPS configuration
Certificate location
Private key location
Encryption key locations
Logging configuration
HTTPHandler configuration
```

The server also loads:

```text
Server_Config/http_config.json
```

when each `HTTPHandler` instance is initialized.  

---

# Encryption

The server includes Fernet-based encryption helpers:

```python
encrypt(data, key)
decrypt(data, key)
```

At startup, the server loads several key files and decrypts the configured `pepper` value.

The implementation uses:

```python
from cryptography.fernet import Fernet
```



---

# HTTPS

HTTPS is implemented in `webserver_ipv4_ssl.py`.

The HTTPS startup sequence is:

```text
Start
 │
 ▼
Create IPv4 TCP socket
 │
 ▼
Check HTTPS enabled
 │
 ▼
Create SSLContext
 │
 ▼
Load certificate
 │
 ▼
Load private key
 │
 ▼
bind()
 │
 ▼
listen()
 │
 ▼
wrap_socket()
 │
 ▼
listener()
 │
 ▼
Normal HTTPHandler pipeline
```

The same request-processing machinery is therefore used after the TLS layer has established the socket. 

---

# HTTP-to-HTTPS Redirect

The non-SSL server can be configured to force HTTPS.

When enabled, `respond_to_request()` changes the requested path to:

```text
/redirecttossl
```

and places the original path into the request parameters.

This allows the application's configured redirect action to generate the redirect response. 

---

# Database Access

`HTTPHandler` provides:

```python
create_sqlite_connection(db_file)
```

which creates a SQLite connection inside the configured private database directory.

The method uses the configured:

```text
root-path
private-files
databases
```

path structure. 

---

# Directory Concept

The implementation expects a configuration-driven directory structure similar to:

```text
Project/
│
├── webserver_ipv4.py
├── webserver_ipv4_ssl.py
├── my_http_handler.py
│
├── Server_Config/
│   ├── server_config.json
│   ├── http_config.json
│   └── log.sql
│
├── Actions/
│   ├── GET/
│   ├── POST/
│   ├── PUT/
│   ├── DELETE/
│   ├── CONNECT/
│   ├── OPTIONS/
│   ├── TRACE/
│   └── PATCH/
│
├── Public/
│   └── ...
│
├── Templates/
│   └── ...
│
└── Private/
    └── databases/
        └── ...
```

The exact directory names and locations are controlled by `http_config.json`; the server does not hard-code all of these names.

---

# Complete Request Lifecycle

A normal request can be summarized as:

```text
CLIENT
  │
  │ HTTP request
  ▼
TCP / TLS SOCKET
  │
  ▼
listener()
  │
  ├── Semaphore
  │
  ├── accept()
  │
  └── Thread()
          │
          ▼
    _handle_client()
          │
          ▼
    _recv_http_request()
          │
          ├── Read headers
          ├── Content-Length
          └── Chunked body
          │
          ▼
      HTTPHandler()
          │
          ▼
    respond_to_request()
          │
          ▼
     parse_request()
          │
          ▼
    handle_request()
          │
          ▼
     HTTP method
          │
          ▼
       do_*()
          │
          ▼
   execute_action()
       /         \
      /           \
     ▼             ▼
Python action   Static file
     │             │
     └──────┬──────┘
            ▼
      set_response()
            │
            ▼
      HTTP response
            │
            ▼
      sendall()
            │
            ▼
     close socket
            │
            ▼
   semaphore.release()
```

---

# Threading Model

The server uses a bounded thread-per-connection architecture.

```text
                       LISTENER
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
          Thread 1     Thread 2     Thread 3
             │            │            │
             ▼            ▼            ▼
         Handler A    Handler B    Handler C
             │            │            │
             ▼            ▼            ▼
         Request A    Request B    Request C
```

Each worker receives its own `HTTPHandler` instance.

Shared session state remains class-level and is protected by `RLock`.

The maximum number of active workers is controlled by the configured semaphore.  

---

# Server Startup

The non-SSL server startup sequence is:

```text
Program starts
     │
     ▼
Determine absolute path
     │
     ▼
Change working directory
     │
     ▼
Load server_config.json
     │
     ▼
Load encryption keys
     │
     ▼
Decrypt configuration values
     │
     ▼
Load my_http_handler.py
     │
     ▼
Create HTTPHandler
     │
     ▼
non_ssl_server()
     │
     ▼
Create TCP socket
     │
     ▼
bind()
     │
     ▼
listen()
     │
     ▼
listener()
     │
     ▼
Wait for clients
```

The supplied IPv4 server starts its main server process by calling `non_ssl_server()` after configuration and handler initialization. 

---

# Dependencies

The implementation uses Python standard-library modules including:

```text
os
ssl
json
time
atexit
socket
secrets
sqlite3
datetime
traceback
subprocess
threading
```

It also depends on:

```text
cryptography
```

for Fernet encryption.

The MySQL logging path additionally imports:

```text
mysql.connector
```

when MySQL logging is configured.  

---

# Security Considerations

This server provides several security-related mechanisms, including:

* TLS support
* Encrypted configuration material
* Random session identifiers
* Session expiration
* `SameSite=Strict` session cookies
* Maximum HTTP header size
* Socket timeouts
* Maximum concurrent worker threads
* Serialized access to shared session state
* HTTP request validation

However, this is a custom HTTP server and application framework. Deployments should therefore be reviewed carefully before being exposed to an untrusted network.

In particular, the framework intentionally executes application-controlled Python files using:

```python
exec(action_script)
```

and executes embedded Python in templates.

Action and template files should therefore be treated as executable server-side code rather than ordinary untrusted content.  

---

# Design Philosophy

The server separates responsibilities into several layers:

```text
┌─────────────────────────────────────────────┐
│ Network                                      │
│ socket / TCP / TLS                           │
├─────────────────────────────────────────────┤
│ HTTP Transport                               │
│ request reception / body framing             │
├─────────────────────────────────────────────┤
│ HTTP Protocol                                │
│ request parsing / methods / headers          │
├─────────────────────────────────────────────┤
│ Application Routing                          │
│ actions / static files / errors              │
├─────────────────────────────────────────────┤
│ Application State                            │
│ sessions / authentication / cookies          │
├─────────────────────────────────────────────┤
│ Presentation                                │
│ templates / generated HTML                   │
├─────────────────────────────────────────────┤
│ Persistence / Operations                      │
│ SQLite / MySQL logging / application DBs     │
└─────────────────────────────────────────────┘
```

This architecture allows the low-level socket listener to remain largely independent of the application's request-handling logic.

---

# Summary

This project implements a custom Python web server rather than relying on Python's higher-level HTTP server frameworks.

At its core, the system performs:

```text
Socket
  ↓
Connection
  ↓
Worker Thread
  ↓
HTTP Message Reception
  ↓
HTTP Parsing
  ↓
Method Dispatch
  ↓
Dynamic Action / Static File
  ↓
Response Construction
  ↓
HTTP Response
  ↓
Socket Close
```

HTTPS adds a TLS layer around the socket, while the same listener and `HTTPHandler` architecture processes the resulting connection.

The `HTTPHandler` additionally provides application-level sessions, cookies, authentication state, template execution, database connectivity, static resources, dynamic Python actions, and configurable error handling.

This is ready to use as a `README.md`.
