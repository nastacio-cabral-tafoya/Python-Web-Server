# Tostada Web Server

**Tostada** is a custom HTTP/HTTPS web server and Python web framework built from the ground up using Python's networking and standard-library facilities.

The project is designed to provide the underlying infrastructure for web applications while giving the developer direct control over the HTTP server, request handling, routing, sessions, authentication, templating, TLS, database connectivity, logging, and deployment environment.

Tostada is currently deployed on an **AWS EC2 instance running Ubuntu Server** and is used as the foundation for web applications hosted on the server.

---

## Overview

Tostada is intentionally built as multiple layers:

```text
                    Internet
                       │
                       ▼
                 AWS EC2 Instance
                       │
                       ▼
                  Ubuntu Server
                       │
                 ┌─────┴─────┐
                 │           │
                 ▼           ▼
             HTTP :80    HTTPS :443
                 │           │
                 ▼           ▼
        webserver_ipv4.py   webserver_ipv4_ssl.py
                 │           │
                 └─────┬─────┘
                       │
                       ▼
                Tostada Framework
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
       Actions     Templates     Sessions
          │            │            │
          └────────────┼────────────┘
                       │
                       ▼
                     MySQL
```

The web server itself is responsible for accepting network connections and processing HTTP traffic. The framework layer provides the mechanisms required to build applications on top of the server.

---

# Features

## HTTP Server

Tostada implements its own HTTP server using Python sockets rather than relying on a traditional web server such as Apache or Nginx.

The server handles:

- TCP connections
- HTTP request processing
- HTTP headers
- request bodies
- `Content-Length`
- chunked transfer encoding
- HTTP methods
- request routing
- response generation
- concurrent client connections

Client connections are handled using worker threads, with the number of simultaneous workers controlled by the server configuration.

---

## HTTPS and TLS

Tostada supports HTTPS using Python's `ssl` implementation.

The HTTPS server:

1. Creates a TCP listening socket.
2. Creates a TLS server context.
3. Loads the configured certificate and private key.
4. Wraps the listening socket with TLS.
5. Passes the resulting connection into the Tostada request-handling system.

TLS is therefore handled directly by the Tostada HTTPS server rather than being terminated by a reverse proxy.

Public and private TLS material is stored within the application's controlled filesystem and made available to the dedicated Tostada service account.

---

## Application Framework

Tostada provides an application layer above the HTTP server.

Applications can use:

- Request handling
- HTTP method dispatch
- Actions
- Dynamic HTML generation
- Templates
- Sessions
- Cookies
- Authentication
- Database connectivity
- Logging
- Server configuration

Application actions are dynamically loaded by the HTTP handler, allowing application functionality to be separated into individual action modules.

This allows an application to be developed independently of the lower-level HTTP implementation.

---

# Threading Model

Tostada uses a threaded request model.

When a client connects, the server creates a worker thread to handle the connection:

```text
Client
  │
  ▼
Listening socket
  │
  ▼
Worker thread
  │
  ▼
HTTPHandler
  │
  ▼
Application action
```

The server limits the number of concurrent worker threads through its configuration.

## Thread-local database connections

Database access is designed around the same threading model.

The framework exposes a global `db_connection` interface to the HTTP handler and application actions, while the actual database connection is maintained separately for each worker thread.

Conceptually:

```text
Tostada Process
│
├── db_connection interface
│
├── Thread 1
│   ├── HTTPHandler
│   ├── Action
│   └── MySQL connection 1
│
├── Thread 2
│   ├── HTTPHandler
│   ├── Action
│   └── MySQL connection 2
│
└── Thread 3
    ├── HTTPHandler
    ├── Action
    └── MySQL connection 3
```

This allows existing application actions to use `db_connection` without sharing one physical MySQL connection between concurrent worker threads.

Connections are closed when their associated request thread finishes.

---

# Sessions and Cookies

Tostada provides session management using HTTP cookies.

A session identifier is stored in a cookie configured with attributes such as:

- `Max-Age`
- `SameSite`

The session system allows applications to maintain state across HTTP requests while keeping session data associated with the appropriate client.

---

# Authentication

The framework provides infrastructure for authenticated application access.

Authentication state is integrated with the server's session mechanism so that authenticated requests can be associated with the appropriate application user.

---

# Dynamic Actions

Application functionality is organized into individual action scripts.

The HTTP handler can load and execute the appropriate action based on the incoming request.

This allows an application to be structured around individual endpoints rather than placing all application logic directly inside the HTTP server.

Conceptually:

```text
HTTP Request
     │
     ▼
HTTPHandler
     │
     ▼
Route / Action
     │
     ▼
Action Script
     │
     ├── Database
     ├── Session
     ├── Authentication
     └── Response
```

---

# Database

Tostada supports database-backed applications.

The deployed environment uses **MySQL**.

Database configuration is supplied through the server configuration system rather than being hard-coded into individual application actions.

The framework also retains support for SQLite for applications that do not require a MySQL server.

---

# Logging

The server maintains application/server logging to assist with:

- startup diagnostics
- request processing
- authentication events
- application errors
- server errors
- debugging
- operational troubleshooting

Logs are particularly useful when diagnosing problems across the different layers of the system.

---

# Deployment

Tostada is deployed on an AWS EC2 instance running Ubuntu Server.

The application is installed under:

```text
/tostada
```

The directory and its contents are owned by:

```text
tostada:tostada
```

The Tostada server runs as a dedicated Linux service account named:

```text
tostada
```

The account is not a sudo user and is not intended to have administrative access to the rest of the operating system.

---

# systemd Integration

Tostada is managed by systemd.

The service runs using the dedicated `tostada` user and uses `/tostada` as its working/application directory.

The deployment uses Linux capabilities to permit the service to bind to privileged network ports without requiring the application itself to run as root.

The resulting privilege model is:

```text
root
 │
 ├── Ubuntu/system administration
 │
 └── systemd
       │
       ▼
   tostada.service
       │
       ▼
   User: tostada
       │
       ▼
   /tostada
```

This prevents the web server from requiring unrestricted root privileges.

---

# Filesystem Isolation

The application is isolated under:

```text
/tostada
```

The directory is owned by the `tostada` account and is protected through normal Unix filesystem permissions.

The service account does not have sudo privileges and is intended to access only the files and resources necessary for the application.

This provides a security boundary between the application and the rest of the Ubuntu installation.

---

# File Browser Quantum

**File Browser Quantum** is installed alongside Tostada to provide browser-based administration and development access to the application filesystem.

File Browser runs under the same:

```text
tostada:tostada
```

service identity and is configured with `/tostada` as its accessible base path.

Therefore:

```text
File Browser
     │
     ▼
   tostada
     │
     ▼
 /tostada
```

File Browser does not provide general administrative access to the Ubuntu filesystem.

This allows the application files to be managed remotely through a web interface while retaining the same operating-system privilege boundary used by the Tostada server.

---

# Deployment Architecture

The deployed system can be represented as:

```text
                           INTERNET
                              │
                    ┌─────────┴─────────┐
                    │                   │
                 HTTP :80           HTTPS :443
                    │                   │
                    ▼                   ▼
             ┌─────────────┐    ┌─────────────┐
             │ Tostada HTTP│    │Tostada HTTPS│
             │   Server    │    │    Server   │
             └──────┬──────┘    └──────┬──────┘
                    │                  │
                    └────────┬─────────┘
                             │
                             ▼
                      Tostada Framework
                             │
                 ┌───────────┼───────────┐
                 │           │           │
                 ▼           ▼           ▼
              Actions     Sessions    Templates
                 │           │           │
                 └───────────┼───────────┘
                             │
                             ▼
                           MySQL


                    Ubuntu Server
                    ─────────────
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
       tostada.service       filebrowser.service
              │                     │
        User: tostada         User: tostada
              │                     │
              ▼                     ▼
          /tostada              /tostada
```

---

# Security Model

The deployment intentionally avoids running the web server as root.

The application instead uses:

- A dedicated Unix service account
- Restricted filesystem permissions
- systemd service isolation
- Linux capabilities for privileged port binding
- TLS for encrypted HTTP traffic
- Session-based authentication
- Controlled access to TLS key material
- A restricted File Browser filesystem root

The goal is to minimize the privileges available to the application while still allowing it to perform the operations required to function as a web server.

---

# Directory Structure

The primary application directory is:

```text
/tostada
```

The installation contains components including:

```text
/tostada
├── actions/
├── web/
├── templates/
├── Server_Config/
├── Certifications/
├── documentation/
├── webserver_ipv4.py
├── webserver_ipv4_ssl.py
├── my_http_handler.py
└── start.sh
```

The exact contents may evolve as the framework and applications built on top of it develop.

---

# Development Philosophy

Tostada is intentionally built rather than assembled from a high-level web framework.

The project provides direct exposure to the layers normally hidden by frameworks:

```text
TCP
 ↓
Sockets
 ↓
HTTP
 ↓
TLS
 ↓
HTTP Handler
 ↓
Routing / Actions
 ↓
Sessions / Authentication
 ↓
Templates
 ↓
Database
 ↓
Application
```

This makes Tostada both a usable web framework and an exploration of how web application infrastructure works underneath higher-level abstractions.

---

# Current Deployment Environment

The current deployment includes:

| Component | Technology |
|---|---|
| Cloud | AWS EC2 |
| Operating System | Ubuntu Server |
| Web Server | Tostada |
| Language | Python |
| HTTP | Custom implementation |
| HTTPS | Python TLS / `ssl` |
| Process Manager | systemd |
| Database | MySQL |
| Development/File Management | File Browser Quantum |
| Application User | `tostada` |
| Application Root | `/tostada` |

---

# Project Goals

The long-term goal of Tostada is to provide a lightweight, understandable Python web framework that remains close to the underlying mechanisms of web servers while still providing the abstractions needed to build practical applications.

Rather than hiding the server behind a large framework stack, Tostada is intended to make the entire application path understandable:

> **A request enters the machine, reaches a socket, is processed by Tostada, dispatched to application code, interacts with the database, and produces an HTTP response.**

The framework and its deployment environment are both part of the project.

---

# Applications Built on Tostada

Tostada is intended to serve as the foundation for applications rather than being the application itself.

The framework is being used as the platform for a forthcoming **CSU Global Computer Science capstone application**.

The capstone application will therefore demonstrate the use of Tostada as an application platform while Tostada itself remains a separate underlying software project.

---

# Status

Tostada is an actively developed project.

The server is currently deployed on an AWS EC2 Ubuntu instance and is capable of serving applications over HTTP and HTTPS, with MySQL database integration and a dedicated systemd-managed service account.

The framework continues to evolve as additional requirements and real-world deployment problems are encountered.

---

## Author

**Nastacio Tafoya**

Tostada is a personal software engineering project developed as an exploration of web-server architecture, Python systems programming, web application development, Linux administration, networking, security, and database-backed applications.
