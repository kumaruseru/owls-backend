# 🦉 OWLS Backend

Django REST API backend for OWLS e-commerce platform.

![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)
![DRF](https://img.shields.io/badge/DRF-3.16-red)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)

## ✨ Features

- 🔐 **Authentication** - JWT-based auth with refresh tokens
- 🛍️ **Products** - CRUD with categories, images, and variants
- 🛒 **Cart** - Session-based shopping cart
- 📦 **Orders** - Order management and tracking
- 💳 **Payments** - Stripe, VNPay, MoMo integration
- ⭐ **Reviews** - Product ratings and reviews
- 📧 **Email** - Transactional emails with templates
- ☁️ **Storage** - Cloudflare R2/S3 for media files

## 🛠️ Tech Stack

| Category | Technologies |
|----------|-------------|
| **Framework** | Django 5.2, Django REST Framework |
| **Database** | PostgreSQL, Redis |
| **Auth** | SimpleJWT, OAuth2 |
| **Payments** | Stripe, VNPay, MoMo |
| **Storage** | Cloudflare R2 / AWS S3 |
| **Tasks** | Celery + Redis |
| **Docs** | drf-spectacular (OpenAPI) |

## 📁 Project Structure

```
backend/
├── apps/
│   ├── cart/           # Shopping cart
│   ├── orders/         # Order management
│   ├── payments/       # Payment gateways
│   ├── products/       # Product catalog
│   ├── reviews/        # Product reviews
│   ├── users/          # User accounts
│   └── utils/          # Shared utilities
├── backend/            # Django settings
├── templates/          # Email templates
├── manage.py
└── requirements.txt
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis (for Celery)

### Installation

```bash
# Clone the repository
git clone https://github.com/kumaruseru/owls-backend.git
cd owls-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your configuration

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run server
python manage.py runserver
```

### Environment Variables

Create a `.env` file with:

```env
# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# Database
DATABASE_URL=postgres://user:pass@localhost:5432/owls

# Storage (Cloudflare R2)
USE_R2=False
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_ENDPOINT_URL=
AWS_S3_CUSTOM_DOMAIN=

# Email
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Payments
STRIPE_PUBLIC_KEY=
STRIPE_SECRET_KEY=
VNPAY_TMN_CODE=
VNPAY_HASH_SECRET=
MOMO_PARTNER_CODE=
MOMO_ACCESS_KEY=
MOMO_SECRET_KEY=
```

## 📜 Scripts

| Command | Description |
|---------|-------------|
| `python manage.py runserver` | Start dev server |
| `python manage.py migrate` | Apply migrations |
| `python manage.py createsuperuser` | Create admin user |
| `python manage.py collectstatic` | Collect static files |
| `celery -A backend worker -l info` | Start Celery worker |

## 📚 API Documentation

After running the server, visit:
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/

## 🔗 Related

- [OWLS Frontend](https://github.com/kumaruseru/owls-frontend) - Next.js frontend

## 📄 License

MIT License
