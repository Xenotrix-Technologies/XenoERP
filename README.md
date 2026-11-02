# XenoERP Enterprise Cloud Suite

> Full-Stack Enterprise Resource Planning & CRM Suite built on **React 19 + TypeScript** (Vite & Tailwind CSS) and **Node.js + Express + Prisma ORM** (PostgreSQL).

---

## 🚀 Overview

**XenoERP** is an all-in-one business management, CRM, and ERP solution designed for modern digital agencies, creative studios, and service enterprises. It features multi-tenant organization workspaces, granular role-based access control, sales pipelines, client management, project tasks, automated GST invoicing, quotations, Meta Ads campaign tracking, and video production studio workflows.

---

## 🏗️ Architecture & Modules

The platform is designed as a unified monorepo:

### 🖥️ Frontend (`client/`)
- **React 19 + TypeScript** with Vite bundler
- **Tailwind CSS** for modern, responsive enterprise design
- **React Router 7** for nested routes and authentication guards
- **Lucide React** icon system
- **Axios** with automatic Bearer token injection and error handling

### ⚡ Backend (`server/`)
- **Node.js + Express** REST API
- **Prisma ORM** connecting to Neon PostgreSQL
- **JWT Authentication** supporting bcrypt & legacy Django PBKDF2-SHA256 password hashes
- **Full modular routes**:
  - `/api/auth` — Login, current user context, session tokens
  - `/api/dashboard` — High-level KPI metrics and activity feeds
  - `/api/leads` — Lead capture, scoring, custom stage statuses, pipeline
  - `/api/clients` — Client accounts, active retainers, contracts
  - `/api/projects` — Deliverables, task milestones, kanban statuses
  - `/api/finance` — Incomes, operational expenses, cash flow balance
  - `/api/invoices` — GST invoices, line items, payment tracking
  - `/api/quotations` — Service proposals, estimates, scope items
  - `/api/agreements` — Client contracts, retainers, legal terms
  - `/api/campaigns` — Meta Ads tracking, ad spend, 18% GST, CPR
  - `/api/content-tracker` — Video production pipeline (Ideation, Shooting, Editing, Review, Published)
  - `/api/hr` — Employee directory, designations, attendance, payroll
  - `/api/services` — Product and service catalog, pricing
  - `/api/support` — Helpdesk ticketing system with priorities
  - `/api/settings` — Pipeline stages, workspace profile, departments

---

## ⚡ Quick Start

### 1. Prerequisites
- **Node.js** v18+ or v20+
- **PostgreSQL** database (e.g. Neon, Supabase, local PostgreSQL)

### 2. Environment Setup

Create `server/.env`:
```env
PORT=5000
DATABASE_URL="postgresql://user:password@host/neondb?sslmode=require"
JWT_SECRET="your-secure-jwt-secret-key"
NODE_ENV="development"
```

Create `client/.env`:
```env
VITE_API_URL="http://localhost:5000"
```

### 3. Installation

Install all monorepo dependencies:
```bash
npm run install:all
```

Generate Prisma client:
```bash
npm run db:generate
```

### 4. Running the Development Server

Start both frontend and backend concurrently:
```bash
npm run dev
```

- **Frontend:** `http://localhost:5173`
- **Backend API:** `http://localhost:5000`

### 5. Production Build

To compile both backend TypeScript and frontend Vite assets:
```bash
npm run build
```

---

## 🔒 Authentication & Compatibility

The authentication engine natively verifies:
1. **Django PBKDF2 (`pbkdf2_sha256$`)** — Preserves zero downtime authentication for existing user accounts.
2. **Bcrypt** (`$2a$`, `$2b$`, `$2y$`) — Standard for newly created users and administrators.
3. **Stateless JWT Tokens** — Secure session tokens delivered in `Authorization` headers.
