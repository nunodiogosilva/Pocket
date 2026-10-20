# System Specification & Architecture: BitPocket

## 1. Project Overview & Core Philosophy

**BitPocket** is a universal, open-source, self-hosted personal cloud storage and file management system. Designed from the ground up to be completely operating-system agnostic, BitPocket runs seamlessly on any environment supporting Docker and Docker Compose—including Linux servers, Raspberry Pi units, macOS, and Windows Server.

The application adheres to a strict lightweight resource budget (targeting under 200MB of RAM) to leave ample headroom for system services and secure networking mesh layers. It eliminates complex configuration files, external multi-container dependencies, and heavy server-side processing by utilizing an embedded database architecture and client-side rendering for file previews.

---

## 2. Technical Stack & Architecture

* **Backend Runtime:** Python with FastAPI and SQLModel for high-performance, asynchronous REST API handling.
* **Database & Vector Engine:** SQLite integrated with `sqlite-vec` for lightweight, file-based relational data storage and native vector similarity search.
* **Frontend Application:** Angular coupled with Tailwind CSS, engineered to deliver a modern cloud drive user interface with responsive layouts.
* **Containerization:** Standardized Docker multi-stage builds and Docker Compose orchestration using persistent named volumes to guarantee absolute OS-agnostic portability.
* **Networking & Security Proxy:** Tailscale and Tailscale Funnel, providing encrypted mesh routing, zero-port-forwarding public sharing, and automatic network-layer authentication.

---

## 3. Identity & Authentication Architecture

BitPocket abandons traditional password databases, user registration forms, and custom login UI views by delegating identity management entirely to **Tailscale Identity**.

* **Network-Layer Trust:** When a user accesses the application through the private Tailnet domain, incoming traffic is intercepted and validated by Tailscale's secure boundary proxy.
* **Trusted Header Propagation:** Tailscale Serve automatically injects verified user identity context into proxy request headers—specifically capturing user login identifiers, display names, and profile pictures.
* **Just-In-Time (JIT) Provisioning:** The backend automatically intercepts these identity headers on incoming requests. If an authenticated user interacts with BitPocket for the first time, a corresponding profile is provisioned dynamically within the SQLite database.
* **Security Isolation:** Backend container ports are strictly bound to the local loopback interface on the host machine. This prevents external entities from bypassing the Tailscale proxy layer or spoofing authentication headers over raw local networks.

---

## 4. File Preview & Client-Side Rendering Strategy

To maintain a minimal server resource footprint and ensure universal compatibility across host architectures, BitPocket offloads all file preview and inspection mechanics to the client browser:

* **Zero Server-Side Conversion:** The backend functions purely as a high-speed file storage and streaming layer, avoiding heavy document-conversion daemons or server-side rendering engines.
* **Native Browser Capabilities:** Media files (such as MP4 and MOV videos) and PDF documents are streamed directly into native HTML media elements and embedded document viewers.
* **Dynamic Client-Side Parsers:** Text documents, Markdown notes, and tabular comma-separated values are fetched raw and parsed dynamically inside the Angular application using lightweight client-side execution engines, rendering clean formatting and interactive tables instantly in the user interface.

---

## 5. Semantic Search & Access Control Architecture

BitPocket features local semantic search powered by `sqlite-vec`, allowing users to query files based on conceptual meaning rather than rigid keyword matching.

### Data Ingestion & Embedding Lifecycle

* When text-based assets (such as documents, notes, or extracted text blocks) are uploaded, a local embedding pipeline processes the content into high-dimensional numerical vectors.
* These vector representations are stored alongside relational file metadata inside the embedded SQLite database using vector-optimized virtual storage structures, avoiding the need for standalone vector database servers.

### Strict Access Control Enforcement

To maintain absolute data privacy across multi-user environments or shared nodes, the semantic search subsystem enforces strict ownership and access verification:

* **Authorization Filtering:** Search execution queries are bound explicitly to the authenticated context of the requesting user.
* **Scope Limitation:** The vector similarity search engine restricts query results exclusively to assets owned directly by the user or files explicitly shared with them through authorized collaboration linkages. Unlinked or private assets belonging to other profiles are entirely excluded from vector distance calculations at the database query level.

---

## 6. Public File Sharing Mechanics

For scenarios requiring collaboration with individuals outside the private Tailnet, BitPocket implements secure public link generation:

* **Granular Tokenization:** Users can generate unguessable, cryptographically secure sharing tokens tied to individual file records.
* **Controlled Exposure:** Public endpoints validate tokens independently of user accounts, streaming only the specific authorized file without granting broader access to the underlying storage directory or file structure.
* **Ingress Routing:** Public traffic is routed securely via Tailscale Funnel, providing automated TLS termination and external HTTPS delivery without requiring manual router port configurations or dynamic DNS upkeep.

---

## 7. Deployment & Setup Protocol (Interactive OS-Agnostic Setup Wizard)

To streamline the installation process, BitPocket provides a unified interactive configuration script (`setup.py`) that runs natively on any OS with Python 3 installed (Linux, macOS, Windows, and Raspberry Pi). This wizard automates Steps 3, 4, and 5 by prompting for custom values with sensible defaults, updating configuration files, spinning up Docker containers, and mapping Tailscale proxy routes.

### Step 1: Prerequisites & Repository Initialization

1. Ensure Docker, Docker Compose, Tailscale, and Python 3 are installed and running on your host machine.
2. Clone or download the BitPocket repository and navigate to the root directory.

### Step 2: Execute the Interactive Setup Wizard

Run the universal setup script in your terminal:

```bash
python3 setup.py

```

The script will interactively guide you through configuration with pre-filled defaults:

* **Storage Path** *(Default: `./data/storage` or `/mnt/nas-storage`)*
* **Backend Port** *(Default: `8000`)*
* **Public Base URL / Tailscale Domain** *(Default auto-detected via `tailscale status` or `http://localhost:8000`)*

### Behind the Scenes (What the Wizard Automates):

* **Step 3 (Configuration Generation & Environment Binding):** Dynamically writes your chosen values into the root `.env` file and provisions the local storage directory on your file system.
* **Step 4 (Container Orchestration):** Automatically triggers the build sequence and spins up the stack:
```bash
docker compose up --build -d

```


* **Step 5 (Secure Network Mapping via Tailscale Serve):** Automatically registers your backend service with Tailscale to route encrypted traffic and inject identity headers:
```bash
tailscale serve --bg <PORT>

```



### Step 6: Public Ingress Activation (Optional)

If you wish to allow external file sharing outside your private tailnet, enable Tailscale Funnel on your configured port:

```bash
tailscale funnel <PORT>

```