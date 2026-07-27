# BYTEARENA — by BYTEMONK

**Offline LAN Contest Platform**

A portable, offline-first competitive programming platform that lets colleges, schools, coding clubs, and hackathons run secure programming contests using nothing more than a laptop and a Wi-Fi router. No cloud. No internet. Just code.

---

## Why LAN Instead of Cloud?

| ❌ Cloud Problems | ✅ BYTEARENA Solution |
|---|---|
| Participants can search Google | Contest exists only on LAN |
| Participants can use ChatGPT | Disconnect Wi-Fi → contest disappears |
| Internet reliability is a dependency | Zero hosting infrastructure |
| Hosting costs keep adding up | Completely free to run |

## Architecture

```mermaid
flowchart TB
    subgraph Participant["Participant Laptop"]
        direction TB
        B["Browser (Chrome / Firefox)"]
    end

    subgraph Server["Organizer Laptop"]
        direction TB
        CS["Contest Server (Auth, Timer, API, WebSocket)"]
        JW["Judge Worker (Compile, Test, Verify)"]
        DB[("Database (SQLite / PostgreSQL)")]
    end

    subgraph Network["Network"]
        R["Wi-Fi Router (No Internet WAN)"]
    end

    B <-->|HTTP / WebSocket| R
    R <-->|Ethernet RJ45| CS
    CS <--> DB
    CS -->|Submission Queue| JW
    JW -->|Verdict| CS
    B -.->|POST /heartbeat| CS
```

### Components

- **Contest Server** — Handles authentication, contest timer, problem distribution, submission intake, leaderboard generation, organizer dashboard, and WebSocket push for live updates.
- **Judge Worker** — An independent service that picks submissions from a queue, compiles code, runs hidden testcases, compares output, and returns a verdict. Scales to multiple workers.
- **Database** — SQLite for MVP development; PostgreSQL for production deployments.

## Submission Pipeline

```mermaid
sequenceDiagram
    participant P as Participant
    participant CS as Contest Server
    participant Q as Judge Queue
    participant JW as Judge Worker
    participant DB as Database

    P->>CS: Submit Code
    CS->>DB: Store Submission
    CS->>Q: Enqueue Job
    Q->>JW: Dequeue and Process
    JW->>JW: Compile Code
    JW->>JW: Run Hidden Testcases
    JW->>JW: Compare Output
    JW->>CS: Return Verdict
    CS->>DB: Update Result
    CS-->>P: Live Leaderboard Update (WebSocket)
    Note over CS,P: End-to-end under 2 seconds
```

## Network Topology

```mermaid
flowchart LR
    R["LAN Router (No Internet WAN)"]
    OL["Organizer Laptop (contest.local)"]
    P1["Participant 1"]
    P2["Participant 2"]
    PN["Participant N"]

    R -->|RJ45 Ethernet| OL
    R -->|Wi-Fi| P1
    R -->|Wi-Fi| P2
    R -->|Wi-Fi| PN
```

Organizer on Ethernet (RJ45) · Participants on Wi-Fi · No internet access.

## Features

- **Scoring System** — Every submission timestamped. Leaderboard ranks by problems solved and first-accepted time.
- **Live Leaderboard** — WebSocket-driven real-time updates. Rank changes appear instantly.
- **Manual Review** — Organizer can review every submission — source code, execution stats, timeline — then approve, reject, or flag.
- **Organizer Dashboard** — Live view of timer, participants, submissions, judge queue, server health, and warnings.
- **Connection Monitoring** — Heartbeat system and browser event logging. Know who disconnects, switches tabs, or exits fullscreen.
- **Anti-Cheating** — Four layers: LAN isolation, heartbeat, browser event logging, and internet detection.

## Two-Phase Evaluation

```mermaid
flowchart LR
    subgraph Live["During Contest"]
        A[Submit Code] --> B{Auto Judge}
        B -->|AC| C[Live Leaderboard - Provisional]
        B -->|WA| D[Show Verdict]
    end

    subgraph Post["Post-Contest"]
        E[Manual Review] --> F[Time Complexity Analysis]
        F --> G[Final Leaderboard]
    end

    C --> E
    D --> A
```

1. **Live Leaderboard (Provisional)** — During the contest, every accepted submission updates a live leaderboard via WebSockets using correctness and time-to-solve.
2. **Post-Contest Analysis (Ultimate)** — After the contest, the system analyzes every accepted solution's time complexity in a single batch. The final leaderboard factors in solve time, time complexity, and manual review.

## Contest Lifecycle

```mermaid
flowchart LR
    A["01  Create Contest"] --> B["02  Upload Problems"]
    B --> C["03  Start Server"]
    C --> D["04  Join Wi-Fi"]
    D --> E["05  Login and Compete"]
    E --> F["06  Auto Judge"]
    F --> G["07  Live Leaderboard"]
    G --> H["08  Review and Publish"]
```

## Anti-Cheating Strategy

```mermaid
flowchart TD
    L1["Layer 1: LAN Isolation - No internet = no search, no AI"]
    L2["Layer 2: Heartbeat - POST /heartbeat every few seconds"]
    L3["Layer 3: Browser Events - Tab switches and fullscreen exits logged"]
    L4["Layer 4: Internet Detection - Probes public endpoint periodically"]

    L1 --> L2 --> L3 --> L4
```

| Layer | Method | Detection |
|---|---|---|
| 1 | LAN Isolation — Contest exists only inside local network | Disconnect → contest disappears |
| 2 | Heartbeat — Browser sends `POST /heartbeat` every few seconds | Organizer sees disconnects instantly |
| 3 | Browser Events — Tab switches, window blurs, fullscreen exits | Logged live on dashboard with timestamps |
| 4 | Internet Detection — Browser probes public endpoint periodically | Warning flagged on dashboard and participant screen |

## Tech Stack

```mermaid
flowchart LR
    subgraph Frontend["Frontend"]
        RE[React]
        TW[TailwindCSS]
        ME[Monaco Editor]
        RQ[React Query]
    end

    subgraph Backend["Backend"]
        FA[FastAPI]
        SA[SQLAlchemy]
        WS[WebSockets]
    end

    subgraph Database["Database"]
        SL[SQLite - MVP]
        PG[PostgreSQL - Production]
    end

    subgraph Judge["Judge Engine"]
        PY[Python]
        QS[Queue System]
        MW[Multi-Worker]
        DK[Docker - Phase 3]
    end

    Frontend <--> Backend
    Backend <--> Database
    Backend <--> Judge
```

| Area | Technologies |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite (MVP), PostgreSQL, WebSockets |
| Frontend | React, TailwindCSS, Monaco Editor, React Query |
| Judge & Networking | Python, Queue System, Multi-Worker, Docker (Phase 3), mDNS |

## Project Layout

```
Contest/
├── Problems/
│   ├── A/
│   │   ├── statement.md
│   │   ├── tests/
│   │   └── config.json
│   ├── B/
│   └── C/
├── Submissions/
│   ├── Alice/
│   └── Bob/
├── Database/
├── Logs/
└── Config/
```

## Development Roadmap

```mermaid
gantt
    title BYTEARENA Roadmap
    dateFormat YYYY-MM-DD
    axisFormat %Y Q%q

    section MVP
    Contest Creation           :done, p1a, 2026-01-01, 60d
    LAN Hosting and Login      :done, p1b, 2026-02-01, 45d
    Problem Viewing and Submit :done, p1c, 2026-03-01, 45d
    Auto Judge and Leaderboard :done, p1d, 2026-04-01, 45d
    Manual Review              :done, p1e, 2026-05-01, 30d

    section Enhancement
    Captive Portal             :active, p2a, 2026-06-01, 30d
    Practice Mode              :p2b, 2026-06-15, 30d
    Clarifications             :p2c, 2026-07-01, 30d
    Contest Templates          :p2d, 2026-07-15, 30d
    mDNS Auto-Discovery        :p2e, 2026-08-01, 30d

    section Advanced
    Docker Sandboxing          :p3a, 2026-09-01, 45d
    Plagiarism Detection       :p3b, 2026-10-01, 45d
    ICPC Penalties             :p3c, 2026-10-15, 30d
    Analytics and Import Export :p3d, 2026-11-01, 45d
```

### Phase 1 — MVP (Core Platform)
Contest creation, LAN hosting, login, problem viewing, code submission, automatic judging, leaderboard, and manual review.

### Phase 2 — Enhancement (Quality of Life)
Captive portal, practice mode, clarification requests, contest templates, and mDNS auto-discovery.

### Phase 3 — Advanced (Production Ready)
Docker sandboxing, multi-worker judge pool, plagiarism detection, ICPC penalties, contest import/export, and analytics dashboard.

## MVP Deliverables

- **Organizer**: Create Contest, Upload Problems, Start Contest, Review Submissions, Publish Results
- **Participant**: Join LAN, Login, Read Problems, Submit Code, View Verdict, View Leaderboard
- **System**: Offline Hosting, Auto Testcase Verification, Timestamp Tracking, Live Leaderboard, Manual Review

## Getting Started

> Coming soon — the project is currently in the planning/design phase.

---

<p align="center">No Cloud. No Internet. Just Code.</p>
