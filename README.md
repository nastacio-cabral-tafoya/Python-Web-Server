# Tostada Web Server

## Overview

Tostada is a custom Python-based IPv4 web server and application framework. It implements its own TCP listener, HTTP/1.x request parsing, routing, response generation, static-file serving, dynamic Python actions, sessions/cookies, configurable error handling, database connectivity, logging, and optional HTTPS/TLS support.

The current implementation is split primarily across:

- `webserver_ipv4.py` — non-TLS HTTP server process.
- `webserver_ipv4_ssl.py` — TLS/HTTPS server process.
- `my_http_handler.py` — shared HTTP request/response and application handler.
- `Server_Config/server_config.json` — server/runtime configuration.
- `Server_Config/http_config.json` — HTTP handler/application configuration.
- `web/actions/` — method-specific dynamic Python actions.
- `web/files/public/` — publicly served files.
- `web/files/private/` — private application data and databases.
- `web/templates/` — server-side templates.
- `Server_Config/SQL_Scripts/` — database initialization scripts.
- `web/certifications/` — application certificate/key storage area.
- `start.sh` — process launcher used by the systemd service.

The production deployment observed in the architecture record runs the application from `/tostada` under a dedicated `tostada` system account. The service is managed by systemd as `tostada.service`. The recorded deployment runs both the HTTP and HTTPS Python processes concurrently. fileciteturn0file0L181-L230

---

# 1. Architecture

At a high level:

```text
                         Internet / Client
                                |
                    +-----------+-----------+
                    |                       |
                  HTTP                    HTTPS
                  TCP/80                  TCP/443
                    |                       |
                    v                       v
          webserver_ipv4.py       webserver_ipv4_ssl.py
                    |                       |
                    +-----------+-----------+
                                |
                                v
                         HTTPHandler
                      (my_http_handler.py)
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
         GET/HEAD          POST/PUT/etc.       Errors
             |                  |                  |
             +------------------+------------------+
                                |
                       execute_action()
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
       Python action script                  Public file
       web/actions/<method>/                 web/files/public/
              |
              v
        Application logic
              |
       +------+------+
       |             |
       v             v
   Sessions       Database
   / Cookies      SQLite / MySQL
       |
       v
    Response
       |
       v
     Client
```

The two server processes intentionally share the same application handler and configuration model. The non-SSL process binds the configured non-SSL port, while the SSL process creates an `SSLContext`, loads the configured certificate/key, binds the configured SSL port, and passes the TLS socket to the same listener implementation. fileciteturn0file3L382-L397 fileciteturn0file1L382-L397

---

# 2. Runtime Environment

The documented production host is an x86-64 Ubuntu 26.04.1 LTS virtual machine running under Xen. The architecture snapshot records a single exposed CPU, approximately 1.9 GiB RAM, a 30 GiB disk, and an ext4 root filesystem. fileciteturn0file0L8-L23 fileciteturn0file0L37-L64 fileciteturn0file0L85-L110

The recorded Python runtime is:

```text
Python 3.14.4
/usr/bin/python3
```

The deployment includes `cryptography` and `mysql-connector-python`; the architecture snapshot records `cryptography 46.0.5` and `mysql-connector-python 26.7.0`. fileciteturn0file0L701-L750

The server's recorded private IPv4 address is `172.31.9.59`. HTTP was observed listening on port 80 and HTTPS on port 443. MySQL was observed bound to loopback on port 3306. fileciteturn0file0L118-L150

> **Deployment note:** The private IP above is an environment snapshot, not an application constant. The actual bind address comes from `server_config.json`.

---

# 3. Process Model

Tostada is not a conventional WSGI/ASGI application. It directly owns its TCP sockets.

The systemd service starts:

```text
/tostada/start.sh
    |
    +-- python3 /tostada/webserver_ipv4.py
    |
    +-- python3 /tostada/webserver_ipv4_ssl.py
```

The recorded systemd unit is configured with:

```ini
[Unit]
Description=Tostada Web Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tostada
Group=tostada
WorkingDirectory=/tostada
ExecStart=/tostada/start.sh
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

The application therefore runs as the unprivileged `tostada` account while retaining the capability required to bind privileged ports such as 80 and 443. fileciteturn0file0L181-L230

The `tostada` account is not permitted to use `sudo` according to the recorded deployment. `/tostada` is also owned by `tostada:tostada` with restrictive directory permissions. fileciteturn0file0L230-L280

---

# 4. Directory Layout

The observed deployment contains the following structure:

```text
/tostada/
├── Documentation/
│   ├── README.md
│   └── Tostada_Capstone_Documentation_Outline.docx
│
├── Server_Config/
│   ├── http_config.json
│   ├── server_config.json
│   └── SQL_Scripts/
│       ├── mysql/
│       └── sqlite/
│
├── web/
│   ├── actions/
│   │   ├── delete/
│   │   ├── get/
│   │   ├── post/
│   │   └── put/
│   │
│   ├── certifications/
│   │   ├── keys/
│   │   └── webserver-certs/
│   │
│   ├── files/
│   │   ├── private/
│   │   └── public/
│   │
│   └── templates/
│
├── create_pepper.py
├── getkey.py
├── log.db
├── log.txt
├── my_http_handler.py
├── start.sh
├── webserver_ipv4.py
└── webserver_ipv4_ssl.py
```

The architecture snapshot also records restrictive ownership/permissions on the application tree and shows the separation between public files, private files, actions, templates, certificates, configuration, and SQL scripts. fileciteturn0file0L230-L280

---

# 5. `webserver_ipv4.py`

## Purpose

`webserver_ipv4.py` is the plain TCP/HTTP entry point.

Its responsibilities are:

1. Load the server configuration.
2. Load encryption-related key material.
3. Decrypt the configured pepper.
4. Load the shared `HTTPHandler` implementation.
5. Initialize the configured database backend.
6. Initialize an `HTTPHandler` instance.
7. Start the non-SSL TCP listener.

The startup sequence is performed directly when the module is executed. fileciteturn0file3L400-L449

## Database initialization

For SQLite, the process creates a connection using the configured database path and enables:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=30000;
```

This is intended to allow concurrent readers and make writers wait rather than immediately failing with `database is locked`. fileciteturn0file3L435-L447

For MySQL, the process imports `mysql.connector` and creates a connection using the configured host, port, database, username, and password. fileciteturn0file3L448-L451

## HTTP listener

The non-TLS listener:

```text
server-host
    |
non-ssl-port
    |
TCP socket
    |
listen(queue-limit)
    |
listener()
```

The server's `non_ssl_server()` function obtains the host and port from configuration, binds the socket, listens using the configured queue limit, and enters the common listener. fileciteturn0file3L382-L397

## Optional HTTP-to-HTTPS redirection

The HTTP process passes:

```text
enable-https.force-ssl.force
enable-https.force-ssl.true-path
```

to the listener. When forced SSL is enabled, the handler replaces the requested path with `/redirecttossl` and supplies the original destination as a query parameter. fileciteturn0file3L382-L397 fileciteturn17file8

---

# 6. `webserver_ipv4_ssl.py`

## Purpose

`webserver_ipv4_ssl.py` provides the TLS-enabled listener.

It follows essentially the same initialization path as the HTTP server but ultimately calls:

```python
ssl_server()
```

The TLS server:

1. Reads `server-host`.
2. Checks that HTTPS is enabled.
3. Reads `ssl-port`.
4. Creates an `ssl.SSLContext` using `ssl.PROTOCOL_TLS_SERVER`.
5. Loads the configured certificate and private key.
6. Binds the TCP socket.
7. Starts listening.
8. Wraps the socket using the SSL context.
9. Passes the resulting TLS socket to `listener()`. fileciteturn0file1L382-L397

The code explicitly disables automatic handshake-on-connect:

```python
context.wrap_socket(
    tcp_socket,
    server_side=True,
    do_handshake_on_connect=False
)
```

The connection is then processed by the common listener/worker path.

---

# 7. Shared Socket Listener

Both HTTP and HTTPS use the same listener architecture.

The listener creates a semaphore:

```python
thread_slots = Semaphore(server_config["max-threads"])
```

For every accepted connection it:

1. Acquires a thread slot.
2. Accepts the connection.
3. Applies a 10-second socket timeout.
4. Starts a daemon worker thread.
5. Releases the semaphore when that worker finishes.

The worker creates a new `HTTPHandler` instance for the connection. This is important because `HTTPHandler` contains mutable per-request/per-response state. fileciteturn0file1L286-L328 fileciteturn0file1L331-L378

Conceptually:

```text
listener
   |
   +-- accept()
   |
   +-- acquire thread slot
   |
   +-- worker thread
          |
          +-- receive HTTP message
          |
          +-- create HTTPHandler
          |
          +-- respond_to_request()
          |
          +-- sendall()
          |
          +-- close()
          |
          +-- release thread slot
```

This is a bounded thread-per-connection design.

---

# 8. HTTP Request Reception

The low-level request receiver is `_recv_http_request()`.

It deliberately handles one HTTP request per TCP connection.

The receive process is:

```text
TCP socket
   |
   v
Read until CRLF CRLF
   |
   +-- validate header size
   |
   +-- parse Content-Length
   |
   +-- or parse Transfer-Encoding
   |
   +-- read complete body
   |
   v
Complete HTTP request bytes
```

The implementation limits the initial header section to 1 MiB and rejects incomplete or malformed headers. It rejects requests containing both `Content-Length` and `Transfer-Encoding`. fileciteturn0file1L119-L198

## Content-Length

When `Content-Length` is present, the receiver continues reading until the specified number of body bytes have arrived. fileciteturn0file1L189-L198

## Chunked transfer encoding

The receiver supports HTTP/1.1 chunked bodies when `Transfer-Encoding` ends in `chunked`.

Chunks are decoded into a normal body and the request is rebuilt so that the handler receives:

```text
Content-Length: <decoded size>
```

instead of the original transfer encoding. fileciteturn0file1L200-L283

---

# 9. `HTTPHandler`

`my_http_handler.py` contains the application's central request/response engine.

The class:

```python
class HTTPHandler:
```

maintains class-level active sessions and a re-entrant lock:

```python
active_sessions = {}
session_lock = RLock()
```

Each request receives a fresh handler instance, while session state is shared between handler instances. fileciteturn0file2L1-L18

---

# 10. Handler Initialization

When an `HTTPHandler` is constructed it loads:

```text
Server_Config/http_config.json
```

through `import_config()`.

This configuration controls items such as:

- HTTP protocol version.
- Default resource.
- Session cookie name.
- Session timeout.
- Application root path.
- Action locations.
- Public/private file locations.
- Content types.
- Error status text.
- Error resource locations.

The actual JSON contents were not included among the four supplied source files, so the exact deployed values should be taken from the server's `http_config.json`.

---

# 11. Request Parsing

`parse_request()` converts raw HTTP bytes/text into the handler's internal request dictionary.

The resulting request state includes:

```text
request["type"]
request["protocol"]
request["path"]
request["path-parameters"]
request["parameters"]
request["Cookie"]
```

The request target is parsed with `urllib.parse.urlsplit()`.

For example:

```text
GET /dashboard?foo=bar HTTP/1.1
```

becomes conceptually:

```text
type            = GET
protocol        = HTTP/1.1
path            = /dashboard
path-parameters = foo=bar
```

Headers are treated case-insensitively for lookup. Cookies are parsed into a dictionary. Common headers are additionally exposed through conventional names such as `Content-Length`, `Content-Type`, `Transfer-Encoding`, `Host`, `Connection`, and `Cookie`. fileciteturn0file2L27-L141

---

# 12. Supported HTTP Methods

The handler explicitly dispatches:

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

Unknown methods result in a `405` response and an `Allow` header listing the supported methods. fileciteturn17file0

## GET

`GET /` maps to the configured default location.

Other GET paths are passed directly to the GET action/file resolution mechanism.

## HEAD

HEAD follows the same resource resolution path as GET, but removes the response body before sending the response.

The response headers are retained. fileciteturn0file2L521-L570

## POST

POST passes the request body to the corresponding POST action.

## PUT

PUT passes the request body to the corresponding PUT action.

## DELETE

DELETE passes the query parameters to the DELETE action.

## CONNECT, OPTIONS, TRACE, PATCH

These methods have their own dispatch functions and are routed through the same action execution system.

---

# 13. Action-Based Application Model

One of the defining features of Tostada is its action system.

Actions are Python source files organized by HTTP method:

```text
web/actions/
├── get/
├── post/
├── put/
├── delete/
└── ...
```

The handler constructs the action path from:

```text
root-path
+
actions root
+
method-specific action directory
+
requested path
+
.py
```

It then reads the Python source and executes it with:

```python
exec(action_script)
```

The action therefore executes inside the handler's Python runtime context. fileciteturn3file7

This is the application's equivalent of a controller/router layer.

---

# 14. Dynamic Action Parameters

Action arguments are parsed with:

```python
urllib.parse.parse_qsl()
```

Blank values are preserved.

The resulting dictionary is made available to the action execution context.

For compatibility, bare query arguments that do not contain `=` are also retained with a value of `None`. fileciteturn3file7

For example:

```text
/foo?name=Bob&active=true
```

becomes conceptually:

```python
parameters = {
    "name": "Bob",
    "active": "true"
}
```

---

# 15. Static File Serving

If an action script cannot be found, `execute_action()` falls back to `get_file_bytes()`.

The handler then attempts to read:

```text
root-path
+
public-files path
+
requested URL path
```

The file is returned as raw bytes.

The response `Content-Type` is selected from the configured extension-to-MIME mapping.

Text and common structured application types receive a UTF-8 charset suffix. fileciteturn3file7

Conceptually:

```text
GET /style.css
       |
       v
Look for:
web/actions/get/style.css.py
       |
       +-- exists --> execute Python action
       |
       +-- missing
             |
             v
Look for:
web/files/public/style.css
             |
             +-- exists --> return file
             |
             +-- missing --> 404
```

This means the action layer takes precedence over static file serving.

---

# 16. Server-Side Templates

The handler contains a template execution mechanism.

Templates are stored under:

```text
web/templates/
```

The template engine supports embedded Python execution markers and uses `template_print()` to collect generated output.

The handler takes the generated output and inserts it back into the template while attempting to preserve the template's surrounding whitespace and indentation.

The resulting page is returned as HTML with:

```text
Content-Type: text/html
Content-Length: <size>
```

The exact template syntax should be learned from the existing templates in the deployment because those files were not among the four supplied source files.

---

# 17. Response Construction

Responses are constructed manually.

`set_response()`:

1. Selects the response body.
2. Encodes string bodies as UTF-8.
3. Preserves byte bodies as-is.
4. Builds the HTTP status line.
5. Adds configured response headers.
6. Adds one `Set-Cookie` header for each queued cookie.
7. Adds the final CRLF separator.
8. Appends the response body. fileciteturn0file2L171-L204

The response is stored in:

```python
self.response
```

Once set, subsequent calls to `set_response()` do nothing.

---

# 18. Redirects

The handler provides:

```python
redirect(path)
```

which creates:

```text
Location: <path>
HTTP status: 302 Found
```

The SSL-force mechanism uses this infrastructure to redirect HTTP requests to HTTPS. fileciteturn0file2L142-L147

---

# 19. Error Handling

Errors are routed through configured error resources.

`set_error()` receives:

```text
error code
parameters
HTTP method
```

and invokes the configured error action/resource.

There is also a recursion guard:

```python
_handling_error
```

so that an error page that itself fails does not recursively invoke the same error mechanism forever.

If an error handler cannot itself be loaded, the handler falls back to directly setting the status response. fileciteturn3file8

The application therefore supports configurable resources for errors such as:

```text
404 Not Found
405 Method Not Allowed
500 Internal Server Error
```

The exact configured mappings are defined outside the supplied four files in `http_config.json`.

---

# 20. Sessions

Sessions are maintained in memory by `HTTPHandler`.

The global structure is:

```python
HTTPHandler.active_sessions
```

Each session contains:

```text
set-date
timeout
parameters
```

and the parameters initially include:

```text
authenticated = False
```

Session methods are protected by a shared `RLock`, allowing multiple worker threads to access session state safely. fileciteturn0file2L210-L257

## Session creation

`set_session()`:

1. Checks for an existing session cookie.
2. Validates the session if present.
3. Refreshes its set date when valid.
4. Otherwise creates a new random session ID.
5. Stores the session in `active_sessions`.
6. Sets a session cookie.

The session ID is generated with:

```python
secrets.token_urlsafe(64)
```

which provides a large random identifier space. fileciteturn0file2L210-L240

## Session timeout

The timeout is configured as an `HH:MM:SS` string.

The helper:

```python
timeout_to_seconds()
```

converts it to seconds.

Session validation compares the current age against the configured timeout. fileciteturn0file1L108-L115 fileciteturn0file2L242-L257

## Authentication state

A session can be marked authenticated with:

```python
authenticate_session(session_id, username)
```

which stores:

```text
authenticated = True
username      = <username>
```

It can be deauthenticated with:

```python
deauthenticate_session(session_id)
```

and completely removed with:

```python
destroy_session(session_id)
```

The handler also provides getters/setters for arbitrary session parameters. fileciteturn0file2L270-L331

---

# 21. Cookies

Cookies are parsed from incoming `Cookie` headers and stored as a dictionary.

Outgoing cookies are generated with:

```python
set_cookie(name, value, cookie_parameters)
```

The current session implementation sets a cookie containing:

```text
Max-Age
SameSite=Strict
Domain=nastacios.com
```

The cookie construction code does not automatically add every modern cookie security attribute; callers are responsible for whatever attributes they supply. fileciteturn0file2L230-L240 fileciteturn0file2L326-L344

---

# 22. Database Support

The server supports two database modes:

```text
SQLite
MySQL
```

The selected backend is controlled by:

```text
server_config["database"]["type"]
```

## SQLite

The main server creates a SQLite connection with a 30-second timeout.

WAL mode and a 30-second busy timeout are enabled during startup. fileciteturn0file3L439-L447

The HTTP handler also provides:

```python
create_sqlite_connection(db_file)
```

which resolves application SQLite databases under the configured private-files database directory. fileciteturn17file8

## MySQL

The server uses:

```python
mysql.connector
```

and connects using configuration-provided:

```text
host
port
database
user
password
```

The architecture snapshot shows the production MySQL server listening on loopback rather than on a public interface. fileciteturn0file0L137-L150

---

# 23. Logging

There are two logging paths.

## Database logger

`logger()` writes structured log records to a database table named:

```text
log
```

For SQLite it loads:

```text
Server_Config/SQL_Scripts/sqlite/initialize_log_table.sql
```

and for MySQL it loads:

```text
Server_Config/SQL_Scripts/mysql/initialize_log_table.sql
```

The recorded fields include:

```text
logdate
logfile
logfunc
loguser
logstr
```

The database transaction is committed after insertion. fileciteturn0file1L24-L89

## Flat-file logger

`_logger_()` writes directly to:

```text
log.txt
```

using a timestamp and a compact:

```text
logfile, logfunc, loguser, logstr
```

format.

This provides a simpler fallback/debugging log in addition to the database logger. fileciteturn0file1L92-L99

---

# 24. Encryption and Secret Material

Both server processes use the `cryptography.fernet.Fernet` implementation.

The helper functions are:

```python
encrypt(data, key)
decrypt(data, key)
```

The server loads several configured key files:

```text
pepperkey
saltskey
userskey
```

and loads an encrypted pepper using the configured pepper key. fileciteturn0file1L16-L22 fileciteturn0file1L414-L429

The design therefore separates secret/key material from the main JSON configuration.

The exact files and generation procedure should be taken from the deployed `server_config.json`, `create_pepper.py`, and `getkey.py`, because those files were not included in the supplied source set.

---

# 25. HTTPS Certificates

The SSL server expects:

```text
cert-location
key-location
```

from `server_config.json`.

It loads them with:

```python
context.load_cert_chain(
    server_config["cert-location"],
    server_config["key-location"]
)
```

The architecture snapshot records a Let's Encrypt certificate deployment for `nastacios.com` under:

```text
/etc/letsencrypt/live/nastacios.com/
```

with the usual:

```text
cert.pem
chain.pem
fullchain.pem
privkey.pem
```

symlinks. fileciteturn0file0L850-L875

The application also has its own certificate-related directories under:

```text
web/certifications/
web/certifications/keys/
web/certifications/webserver-certs/
```

These are separate from the system-level Let's Encrypt tree observed in the deployment.

---

# 26. HTTP → HTTPS Flow

When HTTPS forcing is enabled:

```text
Client
  |
  | HTTP
  v
Port 80
  |
  v
HTTPHandler
  |
  +-- redirect_to_ssl = True
  |
  v
/redirecttossl
  |
  v
302 Found
  |
  +-- Location: HTTPS destination
  |
  v
Client reconnects using HTTPS
  |
  v
Port 443
```

The `true-path` setting determines whether the original requested path is preserved in the redirect information. fileciteturn17file8

---

# 27. Request Lifecycle

A complete request follows this sequence:

```text
1. TCP connection accepted
        |
2. Worker thread allocated
        |
3. Socket timeout configured
        |
4. _recv_http_request()
        |
5. Complete HTTP message assembled
        |
6. HTTPHandler created
        |
7. respond_to_request()
        |
8. parse_request()
        |
9. Optional HTTP -> HTTPS redirect
        |
10. handle_request()
        |
11. Method-specific do_*()
        |
12. execute_action()
        |
13. Python action attempted
        |
14. If no action exists, public file attempted
        |
15. If file fails, configured error handler invoked
        |
16. Response headers/body constructed
        |
17. sendall()
        |
18. Connection closed
        |
19. Thread slot released
```

The handler explicitly resets its per-request state before parsing and processing the request. fileciteturn17file8

---

# 28. One-Request-Per-Connection Model

The socket receiver intentionally handles one HTTP request per connection.

After the response is sent, the worker closes the connection.

This is simpler than implementing persistent HTTP/1.1 connections but means connection establishment/teardown occurs for each request.

The receiver's own documentation explicitly identifies the one-request-per-connection behavior. fileciteturn0file1L119-L125

---

# 29. Concurrency Model

Concurrency exists at two levels:

## Network workers

Each accepted client connection receives a daemon Python thread.

A semaphore limits the number of simultaneously active worker threads.

```text
max-threads
```

therefore represents an important capacity-control setting. fileciteturn0file1L331-L378

## Session synchronization

Shared session state is protected with:

```python
RLock()
```

through the `_synchronized_session_method` decorator. fileciteturn0file2L1-L8

## Database concurrency

SQLite uses WAL and a busy timeout in the main server connection.

---

# 30. Security Model

The current design includes several deliberate security controls:

- The application runs as the dedicated `tostada` user rather than root.
- The service grants only `CAP_NET_BIND_SERVICE`.
- The `tostada` user cannot sudo.
- Application directories are owned by `tostada:tostada`.
- Secret material is loaded from separate files.
- Fernet is used for encrypted secret material.
- Session identifiers are generated using `secrets.token_urlsafe(64)`.
- Session operations are synchronized.
- HTTP headers have basic structural validation.
- Request headers are size-limited.
- `Content-Length` conflicts are rejected.
- Chunked transfer encoding is explicitly parsed.
- HTTPS uses Python's server TLS context.
- HTTP can be forced to HTTPS.
- Private files are separated from public files at the application directory level.
- MySQL is observed listening on loopback in the documented deployment.

The deployment also has AppArmor active at the operating-system level. fileciteturn0file0L230-L280

---

# 31. Important Security Consideration: Dynamic `exec()`

The action framework intentionally executes Python source files:

```python
exec(action_script)
```

This is a fundamental architectural feature, not an incidental implementation detail.

It means:

> Any attacker who can cause an arbitrary `.py` action file to be selected or modified effectively gains code execution inside the web server process.

Therefore:

- Action directories must never be writable by untrusted users.
- Uploaded content must never be blindly placed in an executable action directory.
- URL-to-filesystem mapping must be treated as security-sensitive.
- Application permissions must remain restrictive.
- Backups and deployment tooling must preserve ownership and permissions.
- Any future plugin/action mechanism should be treated as executable code deployment.

The current architecture's restrictive `/tostada` permissions are therefore especially important. fileciteturn0file0L230-L280

---

# 32. Important Security Consideration: Public File Mapping

Static files are resolved from the configured public-files directory by concatenating the requested URL path.

This makes path normalization and containment important security boundaries.

When extending `get_file_bytes()` or changing routing, preserve the invariant that a client URL must not be able to escape the configured public directory.

This README does not claim that every possible traversal case has been independently audited; the supplied implementation should be security-tested before being exposed as a general-purpose public hosting service.

---

# 33. Important Security Consideration: Session Storage

Sessions are stored in process memory:

```python
HTTPHandler.active_sessions
```

Consequences:

- Sessions disappear when the process exits.
- Sessions are not automatically shared between separate processes.
- HTTP and HTTPS are separate Python processes.
- A restart invalidates in-memory sessions.
- Horizontal scaling would require shared session storage or a different session architecture.

The current architecture runs separate HTTP and HTTPS processes, so any future changes involving cross-process session continuity should be considered explicitly.

---

# 34. Important Deployment Consideration: HTTP and HTTPS Are Separate Processes

The architecture currently has:

```text
webserver_ipv4.py
webserver_ipv4_ssl.py
```

as independent Python processes.

Although they share source/configuration and the same conceptual application, they do not share ordinary Python process memory.

That matters for:

- `HTTPHandler.active_sessions`
- module globals
- in-memory caches
- process-local state
- Python-level locks

Database state can be shared because the processes use a common database backend.

---

# 35. Operational Commands

## Check the service

```bash
sudo systemctl status tostada
```

## Restart

```bash
sudo systemctl restart tostada
```

## Stop

```bash
sudo systemctl stop tostada
```

## Start

```bash
sudo systemctl start tostada
```

## Enable at boot

```bash
sudo systemctl enable tostada
```

## Disable at boot

```bash
sudo systemctl disable tostada
```

## View the unit

```bash
systemctl cat tostada
```

## View recent logs

```bash
sudo journalctl -u tostada --no-pager
```

## Follow logs

```bash
sudo journalctl -u tostada -f
```

## Check listeners

```bash
sudo ss -tulpn
```

Expected application listeners in the documented deployment were:

```text
TCP :80   -> webserver_ipv4.py
TCP :443  -> webserver_ipv4_ssl.py
```

The architecture snapshot also shows SSH on port 22 and MySQL on loopback port 3306. fileciteturn0file0L137-L152

---

# 36. Checking the Python Processes

```bash
ps aux | grep -E 'webserver_ipv4|start.sh'
```

or:

```bash
ps auxf
```

The expected process relationship is:

```text
start.sh
├── webserver_ipv4.py
└── webserver_ipv4_ssl.py
```

The documented deployment showed exactly this arrangement. fileciteturn0file0L181-L205

---

# 37. Checking the Database

For MySQL:

```bash
sudo systemctl status mysql
```

Check listeners:

```bash
sudo ss -ltnp | grep 3306
```

The documented deployment uses MySQL 8.4.11 and the server is bound to `127.0.0.1:3306`. fileciteturn0file0L701-L750

For SQLite, inspect the configured SQLite database path and ensure the application user owns the database and has write access.

---

# 38. Deployment Checklist

Before starting Tostada on a new server:

### Operating system

- [ ] Supported Linux/Python environment installed.
- [ ] Python 3 available.
- [ ] Required Python packages installed.
- [ ] System clock configured correctly.
- [ ] DNS points to the server.
- [ ] Firewall/security-group rules permit required traffic.

### Application

- [ ] `/tostada` exists.
- [ ] `tostada:tostada` owns the application tree.
- [ ] `start.sh` is executable.
- [ ] `webserver_ipv4.py` exists.
- [ ] `webserver_ipv4_ssl.py` exists.
- [ ] `my_http_handler.py` exists.
- [ ] `Server_Config/server_config.json` exists.
- [ ] `Server_Config/http_config.json` exists.
- [ ] action directories exist.
- [ ] public/private file directories exist.
- [ ] templates exist.
- [ ] SQL initialization scripts exist.

### Secrets

- [ ] `pepperkey` exists.
- [ ] `saltskey` exists.
- [ ] `userskey` exists.
- [ ] encrypted pepper exists.
- [ ] file permissions prevent unauthorized reads.

### Database

- [ ] SQLite database exists/configured, or
- [ ] MySQL is installed and reachable.
- [ ] database credentials are correct.
- [ ] application user has required database permissions.
- [ ] logging table can be initialized.

### HTTPS

- [ ] Certificate exists.
- [ ] Private key exists.
- [ ] `cert-location` is correct.
- [ ] `key-location` is correct.
- [ ] certificate covers the production hostname.
- [ ] certificate renewal procedure is known.

### systemd

- [ ] `tostada.service` exists.
- [ ] `User=tostada`.
- [ ] `Group=tostada`.
- [ ] `WorkingDirectory=/tostada`.
- [ ] `ExecStart=/tostada/start.sh`.
- [ ] `CAP_NET_BIND_SERVICE` is available if binding 80/443 directly.
- [ ] service enabled if automatic startup is desired.

---

# 39. Development Workflow

A safe development workflow is:

```text
1. Modify source/configuration
        |
2. Run syntax validation
        |
3. Test locally/non-production
        |
4. Review application logs
        |
5. Verify HTTP
        |
6. Verify HTTPS
        |
7. Verify authentication/session behavior
        |
8. Verify database behavior
        |
9. Restart systemd service
        |
10. Confirm listeners/processes
```

Basic syntax checking:

```bash
python3 -m py_compile webserver_ipv4.py
python3 -m py_compile webserver_ipv4_ssl.py
python3 -m py_compile my_http_handler.py
```

The syntax checks should be performed before restarting the production service.

---

# 40. Troubleshooting

## Service fails immediately

Check:

```bash
sudo systemctl status tostada
sudo journalctl -u tostada -n 100 --no-pager
```

Then manually verify:

```bash
cd /tostada
python3 webserver_ipv4.py
```

Only perform direct execution in a controlled maintenance context because it bypasses the normal systemd process supervision.

## Port 80 already in use

```bash
sudo ss -ltnp | grep ':80'
```

Check whether another web server is running.

## Port 443 already in use

```bash
sudo ss -ltnp | grep ':443'
```

## HTTPS fails during startup

Verify:

```text
server_config["enable-https"]["enabled"]
server_config["ssl-port"]
server_config["cert-location"]
server_config["key-location"]
```

Then verify that the certificate and private key can be read by the `tostada` service account.

## Requests hang

Investigate:

- socket timeout behavior;
- thread exhaustion;
- `max-threads`;
- slow action scripts;
- database blocking;
- malformed request bodies.

Check:

```bash
sudo ss -tnp
ps -eLf | grep -E 'webserver_ipv4|python3'
```

## Database locked

For SQLite, verify that WAL mode is active and that database files are writable by the application user.

The main server already configures:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=30000;
```

but application-level connection management still matters. fileciteturn0file3L439-L447

## 404 responses

Determine whether the requested URL is intended to be:

1. a Python action, or
2. a public file.

Check the corresponding:

```text
web/actions/<method>/
web/files/public/
```

locations.

## 500 responses

Check:

```bash
sudo journalctl -u tostada
```

and the application database/file logs.

A 500 may originate from a Python action or from the configured error resource itself.

---

# 41. Observed Production Issues

The architecture snapshot records two segmentation-fault events involving worker threads and OpenSSL libraries:

```text
libssl.so.3
libcrypto.so.3
```

These were recorded by the kernel while the application was running. fileciteturn0file0L701-L850

The recorded events occurred in threads whose names indicate HTTP handling.

This is significant because ordinary Python exceptions do not normally produce native-library segmentation faults. A native crash therefore warrants investigation at the Python/OpenSSL/cryptography/TLS boundary rather than treating it as an ordinary HTTP application exception.

The architecture record also notes that `coredumpctl` was not installed at the time of capture. fileciteturn0file0L701-L850

Recommended diagnostic tooling for a future reproduction:

```bash
sudo apt install systemd-coredump
```

Then inspect:

```bash
coredumpctl list
coredumpctl info
```

Do not assume that the HTTP application itself is the root cause of a native OpenSSL crash; the evidence only establishes that the crashes occurred inside native SSL/crypto libraries while request-handler threads were active.

---

# 42. Known Implementation Characteristics

The current source has several characteristics that developers should understand before modifying it.

## `exec()` is central to the application model

Dynamic actions are Python programs rather than ordinary callback functions.

## The handler is stateful

Each worker gets a new `HTTPHandler` instance because request/response fields are mutable.

## Sessions are process-local

They live in a class-level dictionary.

## HTTP and HTTPS are separate processes

They do not share Python memory.

## One request per connection

The current socket layer closes each connection after one response.

## Error resources are themselves executable/routable resources

A broken error page can therefore create secondary failures; the handler has a recursion guard.

## Configuration is file-based

The server expects JSON configuration rather than command-line flags.

## Database abstraction is lightweight

The server supports SQLite and MySQL but uses explicit backend branches rather than a general ORM/database abstraction.

---

# 43. Configuration Responsibilities

There are two principal configuration files.

## `server_config.json`

Used by the two server entry points.

Based on the source, it provides values for at least:

```text
server-host
non-ssl-port
ssl-port
queue-limit
max-threads
socket-buffer-size

enable-https
enable-https.enabled
enable-https.force-ssl
enable-https.force-ssl.force
enable-https.force-ssl.true-path

cert-location
key-location

pepperkey
saltskey
userskey
pepper

database
database.type
database.sqlite-file
database.mysql.*
```

These names are derived from the source code. The supplied files do not include the actual JSON configuration, so deployment-specific values must be read from the real configuration file.

## `http_config.json`

Used by `HTTPHandler`.

It supplies the handler with values including:

```text
version
default-location
session-cookie-name
session-timeout
root-path
paths
paths.actions
paths.public-files
paths.private-files
content-types
status-codes
status-locations
```

Again, the actual JSON file was not part of the supplied source set.

---

# 44. Extending Tostada

## Add a new GET endpoint

Create a Python action corresponding to the requested URL under:

```text
web/actions/get/
```

For example, conceptually:

```text
GET /example
```

would map toward:

```text
web/actions/get/example.py
```

provided the configured action-root/method paths use the observed layout.

## Add a POST endpoint

Place the corresponding action under:

```text
web/actions/post/
```

The POST body is made available through the handler's request state.

## Add a static resource

Place it beneath:

```text
web/files/public/
```

and ensure its extension is represented in the configured MIME-type mapping.

## Add an error page

Create/configure the appropriate error resource and update `status-locations` in `http_config.json`.

## Add a template

Place the template in:

```text
web/templates/
```

and use the application's established template execution syntax.

---

# 45. Recommended Coding Conventions

When adding actions:

1. Keep request validation at the beginning.
2. Treat all client data as untrusted.
3. Validate numeric values explicitly.
4. Validate file paths before filesystem operations.
5. Avoid shell execution with user-controlled strings.
6. Use parameterized SQL.
7. Do not place secrets in action source files.
8. Use the existing session APIs rather than directly modifying `active_sessions`.
9. Set explicit response content types.
10. Set content length when appropriate.
11. Return an appropriate HTTP status code.
12. Log meaningful application failures without logging secrets.

---

# 46. Production Security Checklist

Before exposing the service publicly:

- [ ] HTTPS is enabled.
- [ ] HTTP redirects to HTTPS if intended.
- [ ] TLS certificate is valid and current.
- [ ] Private keys are not web-accessible.
- [ ] `/web/files/private/` cannot be served directly.
- [ ] Action directories are not writable by untrusted users.
- [ ] Database credentials are protected.
- [ ] Secret key files are protected.
- [ ] Session cookie configuration is reviewed.
- [ ] Path traversal has been explicitly tested.
- [ ] Upload functionality, if added, is isolated from executable directories.
- [ ] SQL statements use parameters for user data.
- [ ] Error responses do not leak stack traces to clients.
- [ ] Logs do not contain passwords, keys, or session tokens.
- [ ] `max-threads` is appropriate for available memory.
- [ ] TLS/native-library stability has been tested under expected concurrency.
- [ ] Backups exist for required persistent data.
- [ ] Certificate renewal has been tested.

---

# 47. Current Production Snapshot

The supplied architecture record describes a running deployment with:

```text
OS:             Ubuntu 26.04.1 LTS
Kernel:         Linux 7.0.0-1014-aws
Architecture:   x86-64
Virtualization: Xen
CPU exposed:    1
Memory:         ~1.9 GiB
Root disk:      ~30 GiB

Application:    Tostada Web Server
HTTP:           TCP/80
HTTPS:          TCP/443
MySQL:          127.0.0.1:3306
SSH:            TCP/22

Application user:
    tostada:tostada

Application root:
    /tostada

Systemd service:
    tostada.service
```

The service was recorded as active and running, with both Python web-server processes underneath `/tostada/start.sh`. fileciteturn0file0L181-L230

---

# 48. Architectural Summary

Tostada can be understood as five major layers:

## Layer 1 — Operating system

Ubuntu/systemd provides:

- process supervision;
- user/group isolation;
- capability management;
- networking;
- filesystem permissions;
- AppArmor;
- service startup/restart.

## Layer 2 — TCP/TLS transport

`webserver_ipv4.py` and `webserver_ipv4_ssl.py` provide:

- IPv4 TCP sockets;
- connection acceptance;
- request reception;
- socket timeouts;
- worker threads;
- TLS termination.

## Layer 3 — HTTP engine

`my_http_handler.py` provides:

- request parsing;
- header parsing;
- cookie parsing;
- HTTP method dispatch;
- response generation;
- redirects;
- errors;
- static-file delivery.

## Layer 4 — Application framework

The handler provides:

- Python action execution;
- templates;
- sessions;
- authentication state;
- application cookies;
- application-specific routing.

## Layer 5 — Persistence

The application supports:

- SQLite;
- MySQL;
- database-backed logging;
- application databases;
- filesystem-backed public/private data.

---

# 49. Design Philosophy

Tostada is deliberately built as a self-contained web stack rather than as an application running behind an existing web server framework.

That gives the project direct control over:

- socket creation;
- HTTP parsing;
- TLS configuration;
- request dispatch;
- response construction;
- session state;
- action execution;
- filesystem mapping;
- database access;
- logging.

The tradeoff is that Tostada also owns responsibilities normally delegated to mature HTTP servers and application frameworks.

Consequently, changes to the socket layer, HTTP parser, TLS layer, routing layer, filesystem mapping, or action executor should be considered architectural changes rather than isolated feature modifications.

---

# 50. Source-of-Truth and Scope

This README was generated from the supplied:

```text
system_architecture(1).txt
webserver_ipv4.py
webserver_ipv4_ssl.py
my_http_handler.py
```

The architecture document contains both design/deployment information and a point-in-time server snapshot. The Python files contain the actual implementation logic.

Where the architecture document and source describe the same behavior, the source implementation is treated as authoritative for what the code currently does.

The following were **not** supplied as source files in this documentation pass:

```text
Server_Config/server_config.json
Server_Config/http_config.json
start.sh
web/actions/*
web/templates/*
Server_Config/SQL_Scripts/*
create_pepper.py
getkey.py
systemd unit file itself
```

Therefore this README documents their observed roles and interfaces without inventing their missing contents.

---

# 51. Quick Reference

## Main source files

```text
webserver_ipv4.py
    HTTP entry point

webserver_ipv4_ssl.py
    HTTPS entry point

my_http_handler.py
    HTTP/application framework
```

## Configuration

```text
Server_Config/server_config.json
Server_Config/http_config.json
```

## Dynamic code

```text
web/actions/get/
web/actions/post/
web/actions/put/
web/actions/delete/
...
```

## Static content

```text
web/files/public/
```

## Private content

```text
web/files/private/
```

## Templates

```text
web/templates/
```

## SQL initialization

```text
Server_Config/SQL_Scripts/sqlite/
Server_Config/SQL_Scripts/mysql/
```

## Logs

```text
log.txt
log.db
```

## Service

```text
tostada.service
```

## Runtime

```text
/tostada/start.sh
```

---

# 52. Final Operational Model

The entire server can be reduced to the following mental model:

```text
                         ┌──────────────────────┐
                         │      systemd         │
                         │  tostada.service     │
                         └──────────┬───────────┘
                                    │
                              /tostada/start.sh
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
             HTTP process                     HTTPS process
        webserver_ipv4.py                webserver_ipv4_ssl.py
                    │                               │
                 TCP/80                          TCP/443
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                               HTTPHandler
                                    │
                          ┌─────────┴─────────┐
                          │                   │
                     parse request       session state
                          │                   │
                          v                   v
                    method routing        cookies
                          │
              ┌───────────┼────────────┐
              │           │            │
              v           v            v
            action      static       error
            .py file    file         resource
              │           │            │
              └───────────┼────────────┘
                          │
                          v
                       response
                          │
                          v
                        client

Application persistence:
        ┌──────────────┬──────────────┐
        │              │              │
      SQLite         MySQL          Files
        │              │              │
        └──────────────┴──────────────┘

Security boundary:
    systemd user/capabilities
          +
    filesystem permissions
          +
    secret/key files
          +
    TLS
          +
    session controls
          +
    application validation
```

Tostada is therefore a complete, custom HTTP application stack whose core is the relationship between the two socket servers and `HTTPHandler`. The socket servers provide transport and concurrency; `HTTPHandler` provides HTTP semantics and the application framework; actions, templates, files, sessions, and databases provide the application layer.
