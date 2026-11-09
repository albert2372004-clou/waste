# ♻️ Circular Waste Intelligence System (CWMS)
### B2B Industrial Byproduct Marketplace & Logistics Optimization Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-green.svg)](https://www.djangoproject.com/)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9.4-brightgreen.svg)](https://leafletjs.com/)
[![OpenStreetMap](https://img.shields.io/badge/Map-OpenStreetMap-orange.svg)](https://www.openstreetmap.org/)
[![Status](https://img.shields.io/badge/Academic%20Submission-Final%20Version%20(2026)-blueviolet.svg)](#academic-submission-details)

---

## 📌 1. Project Overview

The **Circular Waste Intelligence System (CWMS)** is an enterprise B2B circular economy platform developed to bridge the gap between industrial waste producers (**Suppliers**) and secondary material reprocessors/manufacturers (**Buyers**).

Instead of allowing high-value industrial byproducts (such as vulcanized scrap rubber, textile trimmings, fly ash, post-industrial polymers, and coir pith) to end up in landfills or incinerators, CWMS facilitates:
1. **Verified Material Exchange**: Trading with compliance documentation (Pollution Control Board permits like KSPCB / GPCB).
2. **Geospatial Logistics & Godown Management**: OpenStreetMap and Leaflet-driven facility dispatch and delivery hubs with exact GPS coordinates.
3. **Dynamic Fair-Rate Pricing**: Real-time rate calculation APIs based on virgin commodity price indices, contamination grade, and transport distance.
4. **Smart Batch Cart & Multi-Supplier Fulfillment**: Splitting and aggregating bulk procurement orders across geographically dispersed warehouses.
5. **Circular Innovation Grants & Pledges**: Crowd-pledging portal to finance green recycling infrastructure.

---

## 🛠️ 2. Technology Stack

- **Backend Framework**: Python 3.10+ / Django 5.2 (MVT Architecture)
- **Database**: SQLite (Development) / MySQL compatible (Django ORM)
- **Mapping & Geocoding**: Leaflet.js v1.9.4, OpenStreetMap Tile Service, Nominatim Reverse Geocoding & Photon API
- **Frontend**: Responsive HTML5, CSS3 Custom Properties (Design System), Vanilla JavaScript (Zero bloated frontend build steps)
- **Security & Auth**: Django Auth with custom Company profiles, OTP-based email verification, cryptographic password hashing, strict CSRF & Referrer policies (`strict-origin-when-cross-origin`)
- **Document & Media Handling**: Pillow 10+, Multi-part file upload for environmental permits and compliance certificates

---

## 🚀 3. Step-by-Step Configuration & Execution Guide

Follow these exact steps to configure, install dependencies, and run the project locally.

### Prerequisites
- **Python 3.10** or higher installed on your computer.
- **Git** installed.

---

### Step 1: Clone the Repository
Open your terminal (PowerShell, Command Prompt, or Bash) and clone the repository:
```bash
git clone https://github.com/albert2372004-clou/waste.git
cd waste
```

---

### Step 2: Set Up a Python Virtual Environment

**On Windows (PowerShell / CMD):**
```powershell
python -m venv env
.\env\Scripts\activate
```

**On macOS / Linux:**
```bash
python3 -m venv env
source env/bin/activate
```
*(Your command line prompt will now show `(env)`).*

---

### Step 3: Install Project Dependencies
Upgrade `pip` and install all necessary packages from `requirements.txt`:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 4: Apply Database Migrations
Initialize the database tables and schema:
```bash
python manage.py migrate
```

---

### Step 5: (Optional) Create an Admin / Superuser
To access the Django Admin Panel (`/admin/`) and Custom Management Dashboard (`/admin-dashboard/`):
```bash
python manage.py createsuperuser
```
Follow the interactive prompts to enter a username, email, and password.

---

### Step 6: Start the Development Server
Launch the local web server:
```bash
python manage.py runserver
```

You should see output similar to:
```
System check identified no issues (0 silenced).
Django version 5.2.x, using settings 'myproject.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

---

### Step 7: Open the Application in Your Browser
Visit the following URLs:
- 🌐 **Public Marketplace & Catalog**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 🔑 **User Login**: [http://127.0.0.1:8000/accounts/login/](http://127.0.0.1:8000/accounts/login/)
- 📝 **Enterprise Registration**: [http://127.0.0.1:8000/accounts/signup/](http://127.0.0.1:8000/accounts/signup/)
- 🗺️ **Manage Facility Godowns**: [http://127.0.0.1:8000/accounts/locations/](http://127.0.0.1:8000/accounts/locations/)
- 🛒 **Batch Shopping Cart**: [http://127.0.0.1:8000/cart/](http://127.0.0.1:8000/cart/)
- 🌱 **Circular Innovation Grants**: [http://127.0.0.1:8000/funding/](http://127.0.0.1:8000/funding/)
- 🛡️ **Custom Admin Dashboard**: [http://127.0.0.1:8000/admin-dashboard/](http://127.0.0.1:8000/admin-dashboard/)

---

## 🧪 4. Running Automated Tests

The application includes comprehensive automated unit and integration tests covering authentication, location management, multi-supplier fulfillment, and pricing calculations:

```bash
python manage.py test
```

Expected output:
```
Ran 55 tests in ~50s
OK
```

---

## 📂 5. Project Directory Structure

```text
waste/
│
├── accounts/                     # User authentication, enterprise profiles, godowns
│   ├── migrations/               # Database migration files
│   ├── services/                 # Email OTP and geocoding services
│   ├── templates/accounts/       # Auth templates (login, signup, OTP, profile, locations)
│   ├── forms.py                  # Signup, profile, location, and password reset forms
│   ├── models.py                 # Custom User Profile, Company, and CompanyLocation models
│   ├── tests.py                  # Test suite for accounts and location modules
│   ├── urls.py                   # Authentication URL routes
│   └── views.py                  # Signup, login, OTP timer, profile & location CRUD
│
├── marketplace/                  # Core e-commerce & circular materials exchange app
│   ├── migrations/               # Material, Listing, Order, Delivery migrations
│   ├── models.py                 # MaterialCategory, Listing, Order, Delivery, Pledges
│   ├── tests.py                  # Order fulfillment, distance scoring & cart tests
│   ├── urls.py                   # Marketplace, cart, checkout, and admin routes
│   └── views.py                  # Catalog, Cart auto-fulfill, checkout, certificates
│
├── myproject/                    # Django project core settings and root URL routing
│   ├── asgi.py
│   ├── settings.py               # Installed apps, DB configuration, Security & Referrer policy
│   ├── urls.py                   # Master URL routing
│   └── wsgi.py
│
├── templates/                    # Global base and layout templates
│   ├── base.html                 # Master layout with design system & Leaflet CDN
│   ├── checkout.html             # Multi-godown delivery selector and checkout
│   ├── index.html                # Marketplace homepage and search filters
│   ├── product.html              # Material listing details with certificate view
│   └── includes/
│       └── location_picker_modal.html # Reusable OpenStreetMap modal component
│
├── media/                        # User-uploaded files (PCB permits, certificates, listing images)
├── db.sqlite3                    # Pre-populated local database with demo companies & materials
├── manage.py                     # Django CLI management utility
├── requirements.txt              # Production/development Python package dependencies
└── README.md                     # Comprehensive project documentation
```

---

## 👥 6. Academic Submission Details

- **Academic Year**: 2026
- **Project Title**: Circular Waste Management System
- **Faculty Coordinator / Guide**: Ms. Jisha Abraham
- **Report Document**: Included in this repository as per prescribed institutional guidelines:
  `2026_GroupID_RegisterNumber_YourName_Class(S3-AorB/I9)_ProjectTitle.pdf`

---

## 📜 7. License & Rights
Developed for academic mini-project submission, 2026. All rights reserved.
